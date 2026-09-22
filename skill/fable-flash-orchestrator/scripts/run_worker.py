#!/usr/bin/env python3
"""Dispatch one task bundle to the DeepSeek worker (Claude Code CLI pointed at DeepSeek's Anthropic API).

The orchestrator (Fable) calls this once per task and waits for it to exit. The worker runs
headless (`claude -p --bare`) inside the target workspace, with an isolated config directory,
the DeepSeek key, the bundled worker instructions, and a bounded tool set. It writes its
completion report to --report; this script writes a sidecar `<report>.run.json` with the
host-observed session id, model, usage and cost (the routing evidence Fable reviews) and
`<report>.stream.jsonl` with the full event stream.

Exit codes: 0 worker finished (STATUS inside the report still needs review), 2 setup error,
3 worker process failed or timed out.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from worker_env import (  # noqa: E402
    DEFAULT_WORKER_MODEL, SUPPORTED_WORKER_MODELS, SetupError, build_worker_env, find_claude_binary, redacted,
)

SKILL_ROOT = Path(__file__).resolve().parents[1]
WORKER_INSTRUCTIONS = SKILL_ROOT / "worker-instructions.md"
DEFAULT_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Edit", "Write", "MultiEdit", "Bash", "TodoWrite"]
DEFAULT_DISALLOWED_TOOLS = ["Agent", "Task", "WebFetch", "WebSearch", "Skill", "NotebookEdit"]


def build_prompt(args: argparse.Namespace, brief_text: str, workspace: Path, report: Path) -> str:
    if args.resume:
        header = (
            f"Correction request for task {args.task_id} from the orchestrator (Fable). "
            "Apply every finding below within your assigned paths, rerun the named verification, "
            f"then overwrite your completion report at {report} and print it as your final message.\n\n"
        )
        return header + (args.message or brief_text)
    return (
        f"You are the implementation worker for task {args.task_id}.\n"
        f"Workspace: {workspace}\n"
        f"Write your completion report to: {report}\n"
        "Use the report format described in your instructions. When the bundle is ready for review, "
        "blocked, or failed, write the report file, then print the same report as your final message.\n\n"
        "=== TASK BRIEF ===\n" + brief_text
    )


def run(args: argparse.Namespace) -> int:
    workspace = Path(args.cwd).resolve()
    if not workspace.is_dir():
        raise SetupError(f"Workspace does not exist: {workspace}")
    brief = Path(args.brief).resolve()
    if not brief.is_file():
        raise SetupError(f"Brief not found: {brief}")
    if not WORKER_INSTRUCTIONS.is_file():
        raise SetupError(f"Bundled worker instructions missing: {WORKER_INSTRUCTIONS}")
    report = Path(args.report).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    config_dir = (workspace / ".fable-flash-worker").resolve()
    config_dir.mkdir(parents=True, exist_ok=True)
    keep = config_dir / ".gitignore"
    if not keep.exists():
        keep.write_text("*\n", encoding="utf-8")

    binary = find_claude_binary(args.claude_bin)
    env = build_worker_env(args.model, config_dir)
    brief_text = brief.read_text(encoding="utf-8")
    prompt = build_prompt(args, brief_text, workspace, report)

    cmd = [
        str(binary), "-p", "--bare", "--verbose",
        "--output-format", "stream-json",
        "--model", args.model,
        "--max-turns", str(args.max_turns),
        "--permission-mode", "acceptEdits",
        "--permission-prompts", "none",
        "--allowedTools", *args.allowed_tools,
        "--disallowedTools", *DEFAULT_DISALLOWED_TOOLS,
        "--append-system-prompt-file", str(WORKER_INSTRUCTIONS),
        "--disable-slash-commands",
        "--strict-mcp-config",
    ]
    if args.max_budget_usd is not None:
        cmd += ["--max-budget-usd", str(args.max_budget_usd)]
    if args.resume:
        cmd += ["--resume", args.resume]
    for extra in args.add_dir:
        cmd += ["--add-dir", extra]

    if args.dry_run:
        print(json.dumps({
            "command": [c if not c.startswith(str(config_dir)) else "<config-dir>" for c in cmd],
            "cwd": str(workspace), "env": redacted(env), "prompt_chars": len(prompt),
            "report": str(report), "note": "Dry run: no worker was started and no request was sent.",
        }, indent=2))
        return 0

    stream_path = report.with_suffix(report.suffix + ".stream.jsonl")
    run_path = report.with_suffix(report.suffix + ".run.json")
    meta: dict = {
        "task_id": args.task_id, "model_requested": args.model, "base_url": env["ANTHROPIC_BASE_URL"],
        "claude_bin": str(binary), "workspace": str(workspace), "report": str(report),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "resumed_from": args.resume,
        "session_id": None, "model_observed": None, "usage": None, "total_cost_usd": None,
        "num_turns": None, "duration_ms": None, "is_error": None, "exit_code": None, "final_text": None,
    }
    started = time.monotonic()
    with stream_path.open("w", encoding="utf-8") as stream:
        proc = subprocess.Popen(
            cmd, cwd=str(workspace), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.stdin and proc.stdout and proc.stderr
        proc.stdin.write(prompt)
        proc.stdin.close()
        last_assistant_text: list[str] = []
        try:
            for line in proc.stdout:
                stream.write(line)
                stream.flush()
                if args.timeout and time.monotonic() - started > args.timeout:
                    proc.kill()
                    meta["is_error"] = True
                    meta["final_text"] = f"Timed out after {args.timeout}s; worker killed."
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("type")
                if kind == "system" and event.get("subtype") == "init":
                    meta["session_id"] = event.get("session_id")
                    meta["model_observed"] = event.get("model")
                elif kind == "assistant":
                    msg = event.get("message") or {}
                    if msg.get("model"):
                        meta["model_observed"] = msg["model"]
                    for block in msg.get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                            last_assistant_text = [block["text"]]
                elif kind == "result":
                    meta["session_id"] = event.get("session_id") or meta["session_id"]
                    meta["usage"] = event.get("usage")
                    meta["total_cost_usd"] = event.get("total_cost_usd")
                    meta["num_turns"] = event.get("num_turns")
                    meta["duration_ms"] = event.get("duration_ms")
                    meta["is_error"] = bool(event.get("is_error"))
                    if event.get("result"):
                        meta["final_text"] = event["result"]
                    models = event.get("modelUsage")
                    if isinstance(models, dict) and models:
                        meta["model_observed"] = ",".join(models.keys())
        finally:
            stderr = proc.stderr.read()
            proc.wait()
    meta["exit_code"] = proc.returncode
    meta["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if meta["final_text"] is None and last_assistant_text:
        meta["final_text"] = last_assistant_text[-1]
    if stderr.strip():
        meta["stderr_tail"] = stderr.strip()[-4000:]

    if not report.is_file():
        body = meta["final_text"] or "(worker produced no final text)"
        report.write_text(
            f"# {args.task_id} implementation report\nSTATUS: failed\n\n"
            "The worker did not write its report file; this file was generated by run_worker.py from the "
            f"final message (exit code {proc.returncode}).\n\n{body}\n", encoding="utf-8",
        )
        meta["report_written_by"] = "run_worker"
    else:
        meta["report_written_by"] = "worker"
    run_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    summary = {k: meta[k] for k in ("task_id", "session_id", "model_requested", "model_observed", "num_turns",
                                    "total_cost_usd", "usage", "exit_code", "is_error", "report_written_by")}
    summary["report"] = str(report)
    summary["run_json"] = str(run_path)
    print(json.dumps(summary, indent=2))
    return 0 if proc.returncode == 0 and not meta["is_error"] else 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--brief", required=True, help="task brief markdown file")
    parser.add_argument("--cwd", required=True, help="workspace the worker runs in")
    parser.add_argument("--report", required=True, help="unique path where the worker writes its completion report")
    parser.add_argument("--model", default=DEFAULT_WORKER_MODEL, choices=SUPPORTED_WORKER_MODELS)
    parser.add_argument("--max-turns", type=int, default=300)
    parser.add_argument("--max-budget-usd", type=float, default=None)
    parser.add_argument("--timeout", type=int, default=0, help="seconds; 0 = no limit")
    parser.add_argument("--allowed-tools", nargs="+", default=DEFAULT_ALLOWED_TOOLS)
    parser.add_argument("--add-dir", nargs="*", default=[])
    parser.add_argument("--resume", metavar="SESSION_ID", help="continue a previous worker session (correction cycle)")
    parser.add_argument("--message", help="text sent on resume instead of the brief (the batched findings)")
    parser.add_argument("--claude-bin", help="explicit Claude Code binary path")
    parser.add_argument("--dry-run", action="store_true", help="print the command and redacted env; start nothing")
    args = parser.parse_args()
    try:
        return run(args)
    except SetupError as exc:
        print(f"SETUP FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
