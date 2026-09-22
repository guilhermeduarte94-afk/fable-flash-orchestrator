#!/usr/bin/env python3
"""Preview/install the Fable + DeepSeek orchestrator skill into Claude Code's user skills folder.

Copies skill/fable-flash-orchestrator to ~/.claude/skills/fable-flash-orchestrator (or --home/.claude/skills).
Dry run by default; --apply writes. Never touches settings.json, credentials, the root model or any key.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required. Nothing was changed.")
sys.dont_write_bytecode = True
BUNDLE = Path(__file__).resolve().parent
sys.path.insert(0, str(BUNDLE / "skill" / "fable-flash-orchestrator" / "scripts"))
from worker_env import SKILL, SetupError  # noqa: E402

SKILL_SOURCE = BUNDLE / "skill" / SKILL
SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".bak"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle_files() -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    for source in sorted(SKILL_SOURCE.rglob("*")):
        if source.is_symlink():
            raise SetupError("The bundle contains an unexpected symlink.")
        if source.is_file() and not (SKIP_NAMES & set(source.parts)) and source.suffix not in SKIP_SUFFIXES:
            files[source.relative_to(SKILL_SOURCE)] = source.read_bytes()
    if Path("SKILL.md") not in files:
        raise SetupError("Bundle is missing SKILL.md.")
    return files


def plan_changes(target: Path) -> list[dict]:
    for item in (target, *target.parents):
        if item.is_symlink():
            raise SetupError(f"Refusing to write through a symlink: {item}")
    changes = []
    for relative, data in bundle_files().items():
        path = target / relative
        if path.exists() and not path.is_file():
            raise SetupError(f"Expected a regular file: {path}")
        old = path.read_bytes() if path.exists() else None
        if old == data:
            continue
        changes.append({"path": path, "action": "create" if old is None else "update", "data": data,
                        "old_sha256": digest(old) if old is not None else None, "new_sha256": digest(data)})
    return changes


def apply_changes(changes: list[dict], target: Path) -> Path | None:
    backup = None
    if any(c["action"] == "update" for c in changes):
        backup = target.parent / f"{SKILL}.backup-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copytree(target, backup)
    for change in changes:
        change["path"].parent.mkdir(parents=True, exist_ok=True)
        change["path"].write_bytes(change["data"])
    receipt = {"installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "target": str(target),
               "backup": str(backup) if backup else None,
               "files": [{"path": str(c["path"].relative_to(target)), "action": c["action"], "sha256": c["new_sha256"]}
                         for c in changes]}
    (target / "install-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", help="home directory (default: the current user's)")
    parser.add_argument("--apply", action="store_true", help="write the files; default is a dry run")
    args = parser.parse_args()
    try:
        home = Path(args.home).expanduser().resolve() if args.home else Path.home()
        target = home / ".claude" / "skills" / SKILL
        changes = plan_changes(target)
        print(f"Target: {target}")
        if not changes:
            print("Already installed: every bundled file matches. Nothing to do.")
        for change in changes:
            print(f"  {change['action']:6} {change['path'].relative_to(target)}")
        if not args.apply:
            print(f"Dry run: {len(changes)} change(s) previewed, nothing written. Re-run with --apply to install.")
            return 0
        backup = apply_changes(changes, target) if changes else None
        print(f"Installed {len(changes)} file(s)." + (f" Previous copy backed up to {backup}." if backup else ""))
        print("No model request was made. Root model, settings.json and credentials were not touched.")
        print("Next: export DEEPSEEK_API_KEY in your shell, restart Claude Code, then run scripts/doctor.py.")
        return 0
    except (SetupError, OSError) as exc:
        print(f"INSTALL FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
