# Fable + DeepSeek Orchestrator

**Save Claude Fable 5.1 for the decisions that need it. Let DeepSeek do the volume.**

A Claude Code skill: Fable stays responsible for planning, architecture,
high-stakes decisions and final review. DeepSeek (`deepseek-flash` by default,
via DeepSeek's Anthropic-compatible API) takes the high-volume work: repository
discovery, implementation, testing and debugging.

Bring an existing plan or start with a feature request. The workflow turns it
into coherent implementation bundles, sends each bundle to a DeepSeek worker,
then returns the completed patch and evidence to Fable for one focused
acceptance pass.

This is a fork of [astra-flash-orchestrator](https://github.com/ethanplusai/astra-flash-orchestrator)
(GPT Astra + Codex) rebuilt for Claude Code. Same workflow, different harness.

> **Status:** early release. Offline tests pass and a dry-run dispatch against
> the real Claude Code binary is verified. The first live delegated task on a
> new machine still needs its `.run.json` inspected to confirm routing.
> Installation never runs paid inference.

## How it works

```text
Fable    →  scope + design + task brief          (this Claude Code session)
DeepSeek →  implement + test + report            (headless `claude -p` process → api.deepseek.com)
Fable    →  review + verify + accept or request fixes
         →  integrate + checkpoint + next task
```

The worker is **not** a native subagent. Claude Code's Agent tool only routes
to Anthropic models, so `scripts/run_worker.py` starts a separate headless
Claude Code process with `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`
and your DeepSeek key. That process:

- runs in an isolated config directory (`<workspace>/.fable-flash-worker/`,
  gitignored): no OAuth, no user hooks, skills, plugins or MCP servers;
- gets only Read/Glob/Grep/Edit/Write/Bash by default; Agent, WebFetch,
  WebSearch and Skill are disallowed, so it cannot recurse or browse;
- receives the full task brief plus `worker-instructions.md` as system prompt;
- is bounded by `--max-turns`, optional `--max-budget-usd` and `--timeout`;
- writes its completion report where Fable told it to, while the script writes
  `<report>.run.json` (session id, observed model, base URL, usage) and
  `<report>.stream.jsonl` (full event stream) as routing evidence.

Correction cycles resume the same worker session with the batched findings.

## Why

| Cost per 1M tokens (Sept 2026 list prices) | deepseek-flash (off-peak / peak) | deepseek-v4-pro (off-peak / peak) |
| --- | ---: | ---: |
| Input, cache miss | $0.15 / $0.30 | $0.66 / $1.32 |
| Input, cache hit | $0.003 / $0.006 | $0.022 / $0.044 |
| Output | $0.60 / $1.20 | $1.98 / $3.96 |

Both have 1M context. Peak is 01:00–04:00 and 06:00–10:00 UTC on Chinese
working days. Delegating the implementation loop moves most tokens to that
price sheet while Fable's judgment stays on the decisions. This package makes
no promise about a specific saving; measure with the DeepSeek usage dashboard.

## Requirements

1. Claude Code (desktop app or CLI) with **Fable 5.1** selected as the session
   model. The skill cannot select or verify the root model.
2. A Claude Code CLI binary for the worker. The desktop app's bundled
   `claude.exe` is found automatically on Windows; otherwise
   `npm install -g @anthropic-ai/claude-code` or set `FABLE_FLASH_CLAUDE_BIN`.
3. Python **3.11+**. No third-party dependencies.
4. A DeepSeek API key exported as `DEEPSEEK_API_KEY` in the shell that launches
   Claude Code. Never paste it into a chat; the scripts read it from the
   environment only and never print it.

## Install

```sh
git clone https://github.com/ethanplusai/astra-flash-orchestrator.git
cd astra-flash-orchestrator
python -B install.py           # dry run: shows what would be written
python -B install.py --apply   # copies the skill to ~/.claude/skills/fable-flash-orchestrator
```

Then restart Claude Code and check the setup (read-only; `--check-api` does a
free GET of DeepSeek's model catalog, no inference):

```sh
python -B ~/.claude/skills/fable-flash-orchestrator/scripts/doctor.py --check-api
```

Uninstall: delete `~/.claude/skills/fable-flash-orchestrator`.

## Use

In a Fable session: "Use fable-flash-orchestrator to plan and build X". Fable
writes `docs/agent-work/<feature>/spec.md` and `tasks/T1.md`, then dispatches:

```sh
python ~/.claude/skills/fable-flash-orchestrator/scripts/run_worker.py \
  --task-id T1 --brief docs/agent-work/x/tasks/T1.md --cwd . \
  --report docs/agent-work/x/reports/T1.md --max-turns 200 --max-budget-usd 2
```

Options: `--model deepseek-v4-pro`, `--timeout <s>`, `--allowed-tools ...`
(for example `"Bash(python -m pytest:*)"` to narrow shell access),
`--resume <session_id> --message "<findings>"` for a correction cycle,
`--dry-run` to print the command and redacted environment without starting
anything.

Trivial edits stay with Fable. Security, payments, tenancy, secrets, migrations
and production-affecting decisions stay with Fable. Nothing is committed,
merged, pushed or deployed by the workflow.

## Layout

```
skill/fable-flash-orchestrator/
  SKILL.md                    orchestration workflow for Fable
  worker-instructions.md      system prompt appended to every DeepSeek worker
  references/                 planning, execution, review, routing
  templates/                  spec, plan.json, task brief, task report, checkpoint
  scripts/run_worker.py       dispatch one bundle to DeepSeek
  scripts/doctor.py           read-only setup check
  scripts/validate_plan.py    structural lint for plan.json
  scripts/worker_env.py       binary discovery + isolated worker environment
examples/invoice-filter/      synthetic plan + brief
tests/                        offline suite (stub CLI, no network)
```

## Limits

- Role isolation, not a sandbox: the worker runs as you on your machine. Keep
  `.env` files and production credentials out of allowed paths.
- `total_cost_usd` in `.run.json` is the CLI's estimate at Anthropic prices, not
  your DeepSeek bill.
- Claude Code CLI flags change; `run_worker.py` is verified against 2.1.271.
- Not affiliated with Anthropic or DeepSeek.
