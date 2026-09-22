#!/usr/bin/env python3
"""Shared helpers: locate the Claude Code binary and build the DeepSeek worker environment.

No network calls and no secrets are printed by anything in this module.
"""
from __future__ import annotations
import glob
import os
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True

SKILL = "fable-flash-orchestrator"
DEEPSEEK_ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
DEEPSEEK_API_HOST = "api.deepseek.com"
DEFAULT_WORKER_MODEL = "deepseek-flash"
SUPPORTED_WORKER_MODELS = ("deepseek-flash", "deepseek-v4-pro")
KEY_ENV = "DEEPSEEK_API_KEY"
BIN_ENV = "FABLE_FLASH_CLAUDE_BIN"
BASE_URL_ENV = "FABLE_FLASH_BASE_URL"  # optional override for an OpenRouter-style Anthropic-compatible proxy

# Parent-session variables that must never leak into the worker process.
STRIP_PREFIXES = ("ANTHROPIC_", "CLAUDE_", "AWS_BEARER_TOKEN_", "GOOGLE_", "DISABLE_")
STRIP_EXACT = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_USE_BEDROCK",
               "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_AUTH_TOKEN"}


class SetupError(RuntimeError):
    pass


def _version_key(path: str) -> tuple:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", path)
    return tuple(int(x) for x in match.groups()) if match else (0, 0, 0)


def find_claude_binary(explicit: str | None = None) -> Path:
    """Locate a Claude Code CLI. Order: explicit arg, FABLE_FLASH_CLAUDE_BIN, PATH, desktop-app bundle."""
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get(BIN_ENV):
        candidates.append(os.environ[BIN_ENV])
    on_path = shutil.which("claude")
    if on_path:
        candidates.append(on_path)
    local = Path.home() / ".claude" / "local" / ("claude.exe" if os.name == "nt" else "claude")
    candidates.append(str(local))
    appdata = os.environ.get("APPDATA")
    if appdata:
        bundled = sorted(glob.glob(os.path.join(appdata, "Claude", "claude-code", "*", "claude.exe")), key=_version_key)
        candidates.extend(reversed(bundled))
    for name in ("~/Library/Application Support/Claude/claude-code/*/claude",):
        candidates.extend(sorted(glob.glob(os.path.expanduser(name)), key=_version_key, reverse=True))
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return path
    raise SetupError(
        "Claude Code CLI not found. Install it (npm install -g @anthropic-ai/claude-code) or set "
        f"{BIN_ENV} to the binary path."
    )


def worker_base_url() -> str:
    url = os.environ.get(BASE_URL_ENV, DEEPSEEK_ANTHROPIC_BASE_URL).strip()
    if not url.startswith("https://"):
        raise SetupError(f"{BASE_URL_ENV} must be an https:// URL.")
    if any(c in url for c in "@?#"):
        raise SetupError(f"{BASE_URL_ENV} must not contain credentials, queries or fragments.")
    return url.rstrip("/")


def build_worker_env(model: str, config_dir: Path, base_url: str | None = None) -> dict[str, str]:
    """Return an isolated environment for the worker process.

    The DeepSeek key is read from DEEPSEEK_API_KEY and passed to the child as ANTHROPIC_API_KEY.
    Every parent Anthropic/Claude Code variable is stripped so the worker cannot fall back to the
    orchestrator's account, and CLAUDE_CONFIG_DIR points to a private folder so the worker sees no
    OAuth credentials, user hooks, skills or MCP servers.
    """
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise SetupError(f"{KEY_ENV} is not set. Export it in your shell; never paste it into an assistant chat.")
    if model not in SUPPORTED_WORKER_MODELS:
        raise SetupError(f"Unsupported worker model {model!r}. Choose one of {', '.join(SUPPORTED_WORKER_MODELS)}.")
    env = {
        k: v for k, v in os.environ.items()
        if k not in STRIP_EXACT and not k.startswith(STRIP_PREFIXES) and k != KEY_ENV
    }
    env.update({
        "ANTHROPIC_BASE_URL": base_url or worker_base_url(),
        "ANTHROPIC_API_KEY": key,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_SMALL_FAST_MODEL": DEFAULT_WORKER_MODEL,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": DEFAULT_WORKER_MODEL,
        "CLAUDE_CONFIG_DIR": str(config_dir),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "PYTHONUTF8": "1",
        "FABLE_FLASH_ROLE": "worker",
    })
    return env


def redacted(env: dict[str, str]) -> dict[str, str]:
    """Environment view safe to print: key values replaced, only worker-relevant keys shown."""
    shown = {}
    for k, v in env.items():
        if k.startswith(("ANTHROPIC_", "CLAUDE_", "DISABLE_", "FABLE_FLASH_")):
            shown[k] = "<redacted>" if "KEY" in k or "TOKEN" in k else v
    return dict(sorted(shown.items()))
