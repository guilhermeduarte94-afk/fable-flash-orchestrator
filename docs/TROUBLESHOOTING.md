# Troubleshooting

## The skill is missing in Claude Code

Check that `python -B install.py --apply` ended with `Installed`, not only a
dry run. The expected file is `~/.claude/skills/fable-flash-orchestrator/SKILL.md`.
Fully restart Claude Code. If you use a custom `CLAUDE_CONFIG_DIR`, pass the
matching `--home`.

## doctor.py: DEEPSEEK_API_KEY is not set

Export it in the shell that launches Claude Code (on Windows: user environment
variable, or `setx DEEPSEEK_API_KEY ...` then a full restart of the app). The
desktop app inherits the environment of the process that started it. Never
paste the key into chat.

## doctor.py: Claude Code CLI not found

Set `FABLE_FLASH_CLAUDE_BIN` to the binary, or install the CLI with
`npm install -g @anthropic-ai/claude-code`. On Windows the desktop app's copy
under `%APPDATA%\Claude\claude-code\<version>\claude.exe` is detected
automatically.

## doctor.py --check-api: HTTP 401/402

The key is wrong or the DeepSeek account has no balance. The check is a free
catalog GET; fix the account, then rerun.

## Worker exits immediately, `.run.json` has `is_error: true`

Read `stderr_tail` in `.run.json` and the first lines of `.stream.jsonl`.
Common causes: an unsupported CLI flag after a Claude Code update (run
`run_worker.py --dry-run` and try the printed command by hand), a network
block on `api.deepseek.com`, or `--max-budget-usd` set too low.

## Worker finished but the report says STATUS: failed and `report_written_by: run_worker`

The worker hit `--max-turns` or stopped without writing its report. The final
message is copied into the report. Raise the turn budget or split the bundle.

## The worker seems to use an Anthropic model

Check `.run.json`: `base_url` must be `https://api.deepseek.com/anthropic` and
`model_observed` a DeepSeek model. `worker_env.py` strips every `ANTHROPIC_*`
and `CLAUDE_*` variable from the parent and sets an isolated config dir, so an
Anthropic model there means the CLI ignored `ANTHROPIC_BASE_URL`; report the CLI
version.

## Permission denied inside the worker

The worker runs with `--permission-prompts none`: any tool outside
`--allowed-tools` is denied, not asked. Widen the list per task, or narrow it
with patterns such as `"Bash(npm test:*)"`.
