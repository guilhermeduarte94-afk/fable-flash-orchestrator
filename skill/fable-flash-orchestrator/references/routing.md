# Routing: Fable in the session, DeepSeek in a child process

The setup has three separate jobs:

1. The Claude Code session (desktop app or CLI) selects the root model. Choose
   Fable 5.1 there; nothing in this package can change or verify it.
2. `scripts/run_worker.py` starts a headless Claude Code process for each task
   bundle with `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` and the
   DeepSeek key, so every worker request goes to DeepSeek.
3. This skill tells Fable when to plan, delegate, review, and integrate.

## Why not a native subagent

The Agent tool and `.claude/agents/*.md` `model:` field only select Anthropic
models. There is no per-subagent base URL. A separate process is the only way to
run a different provider, and it also gives a genuinely clean context, an
isolated config directory, and host-recorded usage.

## Worker models

DeepSeek's Anthropic-compatible API (documented at
api-docs.deepseek.com/guides/anthropic_api) exposes `deepseek-flash` (default,
1M context, vision) and `deepseek-v4-pro`. It supports tool use, streaming,
system prompts and thinking; it ignores `top_k`, `budget_tokens`, `container`
and `mcp_servers`. The worker sets `ANTHROPIC_MODEL` and the default
Opus/Sonnet/Haiku aliases to the chosen model so the CLI cannot pick an
Anthropic model name that DeepSeek would remap silently.

Off-peak DeepSeek prices are half of peak; peak is 01:00–04:00 and 06:00–10:00
UTC on Chinese working days. Check the pricing page for current values; do not
quote prices from memory in reports.

## Isolation guarantees of run_worker.py

- Strips every `ANTHROPIC_*`, `CLAUDE_CODE_*`, `CLAUDECODE`, `CLAUDE_CONFIG_DIR`
  and cloud-provider variable from the inherited environment.
- Sets `CLAUDE_CONFIG_DIR` to `<workspace>/.fable-flash-worker/` (gitignored), so
  the worker has no OAuth credentials, user hooks, skills, plugins or MCP servers.
- Runs `claude -p --bare --strict-mcp-config --disable-slash-commands` with
  `--disallowedTools Agent Task WebFetch WebSearch Skill`: no recursion, no web.
- `--permission-mode acceptEdits --permission-prompts none`: file edits in the
  workspace are allowed; anything outside the allowed tool list is denied, not
  prompted. Bash is allowed by default because the worker must run tests. Narrow
  it per task with `--allowed-tools` (for example `"Bash(python -m pytest:*)"`).
- Passes `--max-turns`, optional `--max-budget-usd` and `--timeout`.

The worker still runs as the user on the user's machine: this is role isolation,
not an operating-system sandbox. Do not delegate work that needs production
credentials, and keep `.env` files out of allowed paths.

## Runtime evidence

`<report>.run.json` records `session_id`, `model_requested`, `model_observed`
(from the CLI's init/result events), `base_url`, `usage`, `total_cost_usd` (the
CLI's estimate using Anthropic prices, not DeepSeek's bill), `num_turns` and exit
status. `<report>.stream.jsonl` holds the full event stream. For the first real
task, confirm `base_url` is the DeepSeek host and `model_observed` is the
DeepSeek model. A worker message saying "I am DeepSeek" is not evidence. Actual
spend comes from the DeepSeek usage dashboard.

## Usage and privacy

Delegation sends the brief, the files the worker reads and its tool output to
DeepSeek. Respect provider-sharing restrictions on private repositories; use
minimal necessary context and avoid production data and secrets. The DeepSeek
key is read from the `DEEPSEEK_API_KEY` shell variable only; never ask for it in
chat and never write it to a file in the repository.
