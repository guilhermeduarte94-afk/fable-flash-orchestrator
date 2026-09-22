# Contributing

Keep changes focused on the Fable → DeepSeek workflow, worker isolation, useful
task contracts and review evidence. Preserve the user's root model, credentials
and security boundaries.

Use Python 3.11+ with no third-party runtime dependencies. Run from the
repository root:

```sh
python -B -m unittest discover -s tests -v
python -B skill/fable-flash-orchestrator/scripts/validate_plan.py examples/invoice-filter/plan.json
DEEPSEEK_API_KEY=placeholder python -B skill/fable-flash-orchestrator/scripts/run_worker.py \
  --task-id T1 --brief examples/invoice-filter/tasks/T1.md --cwd . --report /tmp/T1.md --dry-run
```

Tests use a stub CLI and temporary homes; they never contact a network service.
Do not run `install.py --apply` against your real home just to test a
contribution. Never add paid inference to tests or CI.

For behavior changes, add regression tests. When Claude Code changes a CLI flag
used by `run_worker.py`, update the flag, the README's verified version and the
troubleshooting entry together.

Do not commit credentials, `.fable-flash-worker/` folders, stream logs,
receipts or personal configuration.
