# Changelog

## 2.0.0 — Claude Code fork (2026-09-22)

- Rebuilt for Claude Code: Claude Fable 5.1 orchestrates in the session,
  DeepSeek (`deepseek-flash`, optionally `deepseek-v4-pro`) implements through
  DeepSeek's Anthropic-compatible API.
- Replaced Codex Router / custom-agent routing with `scripts/run_worker.py`,
  which starts a headless `claude -p --bare` process with an isolated config
  directory, the DeepSeek base URL and key, bounded tools, turn and budget
  limits, and records `<report>.run.json` as routing evidence.
- New `scripts/doctor.py` (CLI discovery, key presence, optional free catalog
  check) and `scripts/worker_env.py`.
- `install.py` now copies the skill to `~/.claude/skills/` with dry run, backup
  and receipt; it never touches settings or credentials.
- Plan manifests use `executor: fable | deepseek` and `max_deepseek_workers`.
- Removed Codex-specific docs, policy block, release manifest and benchmark
  claims from the original project.

## Original project (astra-flash-orchestrator ≤ 1.2.0)

## Unreleased

- Support explicit, reviewed DeepSeek V4.1 Flash routes through OpenRouter,
  opencode Go, Command Code, Nous Research and Ollama Cloud while retaining the
  direct DeepSeek API as the default. Existing alternate-route installations
  reuse their validated routing binding on doctor checks and updates.
- Make provider choice fail closed: no catalog auto-detection, silent fallback,
  credential handling or paid certification during package installation.
- State that users enter API keys only through the Router's private local prompt,
  and prohibit installation agents from running `subagents certify`,
  `test-model --live`, smoke tests or other paid probes.
- Detect keys absorbed into `[agents]` by shape instead of by a list of
  anticipated top-level names. A stray key there is read by Codex as an agent
  name and stops the whole config loading, and the previous check only covered
  five names, missing the realtime base-URL keys that caused a real failure.
- Accept a legitimate `[agents]` table containing the recognized scalar settings
  and agent role tables, and reject an agent name whose value is not a table.
- Tell installation agents to select an existing Python 3.11+ interpreter rather
  than assume `python3`, and never to edit `config.toml` to make a check pass.

## 1.2.0 — Measured workflow and simpler installation

- Add a measured efficiency graphic, per-token price comparison and transparent
  benchmark methodology to the README.
- Document thin orchestration as the only supported delegated workflow, not a
  user-selectable mode, while retaining direct handling for trivial work and
  targeted high-assurance review.
- Reduce the normal terminal installation path to a guarded preview and apply;
  keep the offline test suite as optional local verification.
- Remove the unnecessary global subagent-default prerequisite. The installer
  now relies only on its named role's pinned worker settings and explicitly
  warns installation agents not to edit shared Codex model defaults.
- Include SVG documentation assets in release archives.

## 1.1.0 — Thin-root orchestration by default

- Keep Astra to a planning batch, one worker dispatch/wait, one batched acceptance review and the final response for normal phases.
- Make Flash responsible for in-scope repository discovery, implementation, testing, debugging and routine browser/visual QA.
- Remove progress polling, duplicate root investigation and ritual full-suite reruns from the default workflow.
- Consolidate review findings into one correction request and one default correction cycle.
- Retain additional Astra investigation and verification for concrete high-assurance risks.

## 1.0.2 — Native delegation readiness

- Refuse installation when Flash is present but not advertised for native subagents.
- Explain full host-app restart, cached catalogs, and Router commands that can trigger paid verification.
- Distinguish local route selection from runtime capability evidence.

## 1.0.1 — Public repository preparation

- Support the Router's native authenticated `/v1` base path alongside capability paths; retain loopback and URL-shape validation.
- Preserve permissions on an existing installation-backup directory.
- Add regression tests for direct routing, rejected URL shapes and permission preservation.
- Exclude local backup/cache artifacts from installed skill files and release archives.
- Replace private handoff/audit notes with public installation, troubleshooting, contribution and security documentation.
- Add reproducible release inventory and ZIP packaging with integrity checks.

## 1.0.0 — Initial package

- Native Flash builder role, Astra orchestration skill, scoped personal policy, dry run and guarded undo.
- Offline installation tests, configuration doctor, task templates and optional plan validator.
