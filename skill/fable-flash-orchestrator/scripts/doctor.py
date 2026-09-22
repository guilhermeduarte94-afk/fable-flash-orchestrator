#!/usr/bin/env python3
"""Read-only routing check for the Fable → DeepSeek worker setup.

Verifies: Python version, a usable Claude Code CLI, DEEPSEEK_API_KEY presence (value never printed),
the worker base URL, and — only with --check-api — that DeepSeek's /models endpoint lists the worker
model. The /models call is a free catalog GET; it sends no prompt and proves no inference.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from worker_env import (  # noqa: E402
    DEEPSEEK_API_HOST, DEFAULT_WORKER_MODEL, KEY_ENV, SUPPORTED_WORKER_MODELS, SetupError,
    find_claude_binary, worker_base_url,
)


def claude_version(binary: Path) -> str:
    try:
        out = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError(f"Could not run the Claude Code CLI ({type(exc).__name__}).") from None
    if out.returncode != 0:
        raise SetupError("Claude Code CLI returned a non-zero exit for --version.")
    return out.stdout.strip().splitlines()[0] if out.stdout.strip() else "unknown"


def check_api(model: str) -> list[str]:
    key = os.environ[KEY_ENV]
    request = urllib.request.Request(
        f"https://{DEEPSEEK_API_HOST}/models",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=15) as response:
            payload = json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as exc:
        raise SetupError(f"DeepSeek /models returned HTTP {exc.code}; check the key and account.") from None
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SetupError(f"DeepSeek /models check failed ({type(exc).__name__}).") from None
    ids = sorted(str(m.get("id")) for m in payload.get("data", []) if isinstance(m, dict))
    if model not in ids:
        raise SetupError(f"DeepSeek catalog does not list {model}; listed: {', '.join(ids) or 'none'}.")
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_WORKER_MODEL, choices=SUPPORTED_WORKER_MODELS)
    parser.add_argument("--claude-bin")
    parser.add_argument("--check-api", action="store_true", help="GET DeepSeek /models with the key (free, no inference)")
    args = parser.parse_args()
    try:
        if sys.version_info < (3, 11):
            raise SetupError("Python 3.11+ is required.")
        binary = find_claude_binary(args.claude_bin)
        report = {
            "status": "config-ready",
            "python": ".".join(map(str, sys.version_info[:3])),
            "claude_bin": str(binary),
            "claude_version": claude_version(binary),
            "worker_model": args.model,
            "worker_base_url": worker_base_url(),
            "deepseek_key_present": bool(os.environ.get(KEY_ENV, "").strip()),
            "orchestrator": "the current Claude Code session (select Fable 5.1 there; this script cannot change it)",
            "api_checked": False,
            "note": "Static check only. Inference routing is proven by <report>.run.json after the first real task.",
        }
        if not report["deepseek_key_present"]:
            raise SetupError(f"{KEY_ENV} is not set in this shell. Export it (never paste it into chat) and rerun.")
        if args.check_api:
            report["deepseek_models"] = check_api(args.model)
            report["api_checked"] = True
            report["status"] = "catalog-ready"
        print(json.dumps(report, indent=2))
        return 0
    except SetupError as exc:
        print(f"CHECK FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
