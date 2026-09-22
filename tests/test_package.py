from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill" / "fable-flash-orchestrator" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))
import install  # noqa: E402
from validate_plan import PlanError, validate  # noqa: E402
from worker_env import (  # noqa: E402
    DEEPSEEK_ANTHROPIC_BASE_URL, KEY_ENV, SetupError, build_worker_env, find_claude_binary, redacted,
)

# A stand-in for the Claude Code CLI: emits a stream-json transcript and writes the report file
# named in the prompt. It never contacts any network service.
STUB = r'''
import json, os, re, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("9.9.9 (stub)"); sys.exit(0)
prompt = sys.stdin.read()
report = re.search(r"Write your completion report to: (.+)", prompt)
if os.environ.get("STUB_MODE") == "silent":
    print(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "gave up",
                      "session_id": "sess-silent", "num_turns": 1}))
    sys.exit(0)
print(json.dumps({"type": "system", "subtype": "init", "session_id": "sess-123", "model": os.environ.get("ANTHROPIC_MODEL")}))
print(json.dumps({"type": "assistant", "message": {"model": os.environ.get("ANTHROPIC_MODEL"),
                  "content": [{"type": "text", "text": "working"}]}}))
if report:
    with open(report.group(1).strip(), "w", encoding="utf-8") as fh:
        fh.write("# T1 implementation report\nSTATUS: ready_for_review\n")
with open(os.path.join(os.environ["STUB_OUT"], "env.json"), "w") as fh:
    json.dump({k: v for k, v in os.environ.items() if k.startswith(("ANTHROPIC_", "CLAUDE", "DEEPSEEK", "FABLE_FLASH_"))}, fh)
with open(os.path.join(os.environ["STUB_OUT"], "argv.json"), "w") as fh:
    json.dump(args, fh)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "done", "session_id": "sess-123",
                  "num_turns": 3, "total_cost_usd": 0.01, "usage": {"input_tokens": 10, "output_tokens": 5},
                  "modelUsage": {"deepseek-flash": {}}}))
'''


class WorkerEnvTests(unittest.TestCase):
    def test_key_is_required_and_parent_variables_are_stripped(self):
        parent = {"PATH": "x", "ANTHROPIC_API_KEY": "PARENT_SECRET", "CLAUDECODE": "1", "CLAUDE_CONFIG_DIR": "/p",
                  "CLAUDE_CODE_USE_BEDROCK": "1", "ANTHROPIC_BASE_URL": "https://parent", "HOME": "/h"}
        with patch.dict(os.environ, parent, clear=True):
            with self.assertRaises(SetupError):
                build_worker_env("deepseek-flash", Path("/cfg"))
            os.environ[KEY_ENV] = "DS_SECRET"
            env = build_worker_env("deepseek-flash", Path("/cfg"))
        self.assertEqual(env["ANTHROPIC_API_KEY"], "DS_SECRET")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], DEEPSEEK_ANTHROPIC_BASE_URL)
        self.assertEqual(env["ANTHROPIC_MODEL"], "deepseek-flash")
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], str(Path("/cfg")))
        self.assertNotIn("CLAUDECODE", env)
        self.assertNotIn("CLAUDE_CODE_USE_BEDROCK", env)
        self.assertNotIn(KEY_ENV, env)
        self.assertEqual(env["HOME"], "/h")
        self.assertEqual(redacted(env)["ANTHROPIC_API_KEY"], "<redacted>")
        self.assertNotIn("DS_SECRET", json.dumps(redacted(env)))

    def test_unsupported_model_and_bad_base_url_fail_closed(self):
        with patch.dict(os.environ, {KEY_ENV: "k"}, clear=True):
            with self.assertRaises(SetupError):
                build_worker_env("claude-opus-5", Path("/cfg"))
            os.environ["FABLE_FLASH_BASE_URL"] = "http://evil.example/anthropic"
            with self.assertRaises(SetupError):
                build_worker_env("deepseek-flash", Path("/cfg"))

    def test_missing_binary_is_reported(self):
        with patch.dict(os.environ, {"PATH": "", "APPDATA": ""}, clear=True), patch("worker_env.Path.home", return_value=Path("/nonexistent")):
            with self.assertRaises(SetupError):
                find_claude_binary(None)


class RunWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / "repo"
        self.workspace.mkdir()
        self.stub = self.root / "stub_claude.py"
        self.stub.write_text(STUB, encoding="utf-8")
        self.brief = self.root / "T1.md"
        self.brief.write_text("# T1: do the thing\n", encoding="utf-8")
        self.report = self.workspace / "docs" / "reports" / "T1.md"
        self.out = self.root / "out"
        self.out.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def run_worker(self, *extra, mode="ok"):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE"))}
        env.update({KEY_ENV: "DS_TEST_KEY", "STUB_OUT": str(self.out), "STUB_MODE": mode, "PYTHONUTF8": "1",
                    "FABLE_FLASH_CLAUDE_BIN": sys.executable})
        # The stub is a Python script: the "binary" is the interpreter and the script path is prepended via a wrapper.
        wrapper = self.root / ("claude.cmd" if os.name == "nt" else "claude")
        if os.name == "nt":
            wrapper.write_text(f'@"{sys.executable}" "{self.stub}" %*\n')
        else:
            wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{self.stub}" "$@"\n')
            wrapper.chmod(0o755)
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "run_worker.py"), "--task-id", "T1", "--brief", str(self.brief),
             "--cwd", str(self.workspace), "--report", str(self.report), "--claude-bin", str(wrapper), *extra],
            capture_output=True, text=True, env=env, encoding="utf-8",
        )

    def test_dry_run_starts_nothing_and_redacts(self):
        result = self.run_worker("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("DS_TEST_KEY", result.stdout)
        self.assertIn("<redacted>", result.stdout)
        self.assertFalse((self.out / "argv.json").exists())
        self.assertFalse(self.report.exists())

    def test_real_dispatch_records_routing_evidence(self):
        result = self.run_worker("--max-turns", "7", "--max-budget-usd", "1.5")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        argv = json.loads((self.out / "argv.json").read_text())
        env = json.loads((self.out / "env.json").read_text())
        self.assertEqual(argv[:2], ["-p", "--bare"])
        self.assertIn("--max-turns", argv)
        self.assertEqual(argv[argv.index("--max-turns") + 1], "7")
        self.assertIn("--max-budget-usd", argv)
        self.assertIn("Agent", argv[argv.index("--disallowedTools"):])
        self.assertEqual(env["ANTHROPIC_BASE_URL"], DEEPSEEK_ANTHROPIC_BASE_URL)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "DS_TEST_KEY")
        self.assertEqual(env["ANTHROPIC_MODEL"], "deepseek-flash")
        self.assertTrue(env["CLAUDE_CONFIG_DIR"].endswith(".fable-flash-worker"))
        self.assertNotIn("DEEPSEEK_API_KEY", env)
        self.assertTrue((self.workspace / ".fable-flash-worker" / ".gitignore").exists())
        self.assertIn("STATUS: ready_for_review", self.report.read_text(encoding="utf-8"))
        meta = json.loads(Path(str(self.report) + ".run.json").read_text())
        self.assertEqual(meta["session_id"], "sess-123")
        self.assertEqual(meta["model_observed"], "deepseek-flash")
        self.assertEqual(meta["report_written_by"], "worker")
        self.assertEqual(meta["usage"]["output_tokens"], 5)
        self.assertTrue(Path(str(self.report) + ".stream.jsonl").exists())
        self.assertNotIn("DS_TEST_KEY", result.stdout)

    def test_worker_that_writes_no_report_yields_failed_report_and_exit_3(self):
        result = self.run_worker(mode="silent")
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
        self.assertIn("STATUS: failed", self.report.read_text(encoding="utf-8"))
        meta = json.loads(Path(str(self.report) + ".run.json").read_text())
        self.assertEqual(meta["report_written_by"], "run_worker")
        self.assertTrue(meta["is_error"])

    def test_resume_passes_session_and_message(self):
        result = self.run_worker("--resume", "sess-123", "--message", "fix the boundary case")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        argv = json.loads((self.out / "argv.json").read_text())
        self.assertEqual(argv[argv.index("--resume") + 1], "sess-123")

    def test_missing_key_is_a_setup_error(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE", "DEEPSEEK"))}
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "run_worker.py"), "--task-id", "T1", "--brief", str(self.brief),
             "--cwd", str(self.workspace), "--report", str(self.report), "--claude-bin", sys.executable, "--dry-run"],
            capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("DEEPSEEK_API_KEY", result.stderr)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(ROOT / "install.py"), "--home", str(self.home), *args],
                              capture_output=True, text=True)

    def test_dry_run_writes_nothing_then_apply_installs_and_is_idempotent(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / ".claude").exists())
        result = self.cli("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.home / ".claude" / "skills" / "fable-flash-orchestrator"
        self.assertTrue((target / "SKILL.md").is_file())
        self.assertTrue((target / "scripts" / "run_worker.py").is_file())
        self.assertTrue((target / "worker-instructions.md").is_file())
        self.assertTrue((target / "install-receipt.json").is_file())
        self.assertIn("No model request was made", result.stdout)
        again = self.cli("--apply")
        self.assertIn("Already installed", again.stdout)

    def test_modified_file_is_backed_up_on_update(self):
        self.cli("--apply")
        target = self.home / ".claude" / "skills" / "fable-flash-orchestrator"
        (target / "SKILL.md").write_text("local edit", encoding="utf-8")
        result = self.cli("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list((self.home / ".claude" / "skills").glob("fable-flash-orchestrator.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "SKILL.md").read_text(encoding="utf-8"), "local edit")


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / "spec.md").write_text("spec")
        (self.root / "tasks").mkdir()
        (self.root / "tasks" / "T1.md").write_text("brief")
        (self.root / "tasks" / "T2.md").write_text("brief")
        self.plan = {
            "schema_version": 1, "project": "demo", "spec": "spec.md", "max_deepseek_workers": 1,
            "phases": [{"id": "P1", "goal": "g", "depends_on": [], "integration_checks": [{"command": "c", "expected": "e"}]}],
            "tasks": [{"id": "T1", "phase": "P1", "executor": "deepseek", "risk": "normal", "state": "planned",
                       "depends_on": [], "brief": "tasks/T1.md", "allowed_paths": ["src/a.py"],
                       "acceptance": ["a"], "checks": [{"command": "c", "expected": "e"}]}],
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_example_plan_and_executor_names(self):
        self.assertEqual(validate(self.plan, self.root)["status"], "structure-valid")
        example = json.loads((ROOT / "examples" / "invoice-filter" / "plan.json").read_text())
        self.assertEqual(validate(example, ROOT / "examples" / "invoice-filter")["tasks"], 1)
        self.plan["tasks"][0]["executor"] = "flash"
        with self.assertRaises(PlanError):
            validate(self.plan, self.root)

    def test_sensitive_work_stays_with_fable(self):
        self.plan["tasks"][0]["risk"] = "sensitive"
        with self.assertRaises(PlanError):
            validate(self.plan, self.root)
        self.plan["tasks"][0]["executor"] = "fable"
        self.assertEqual(validate(self.plan, self.root)["status"], "structure-valid")

    def test_parallel_group_needs_capacity_and_disjoint_paths(self):
        second = dict(self.plan["tasks"][0], id="T2", brief="tasks/T2.md", allowed_paths=["src/a.py"], parallel_group="g")
        self.plan["tasks"][0]["parallel_group"] = "g"
        self.plan["tasks"].append(second)
        self.plan["max_deepseek_workers"] = 2
        with self.assertRaises(PlanError):
            validate(self.plan, self.root)
        second["allowed_paths"] = ["src/b.py"]
        self.assertEqual(validate(self.plan, self.root)["tasks"], 2)


if __name__ == "__main__":
    unittest.main()
