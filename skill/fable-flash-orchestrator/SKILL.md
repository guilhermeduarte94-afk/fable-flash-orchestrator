---
name: fable-flash-orchestrator
description: Plan and execute substantial multi-file builds, features, migrations, and refactors with Claude Fable 5.1 as orchestrator and DeepSeek (deepseek-flash via its Anthropic-compatible API) as the implementation worker. Use for phased planning and delegated build execution, including existing plans. Skip trivial edits and explicitly single-agent tasks. Worker processes must not invoke this orchestration skill.
---

# Fable plans. DeepSeek implements. Fable accepts.

The worker is a separate headless Claude Code process started by
`scripts/run_worker.py`, pointed at DeepSeek's Anthropic-compatible endpoint. It
is not a native subagent: the Agent tool in this session always routes to
Anthropic models, so never use Agent/Task for the implementation loop. Do not
claim routing is verified from these instructions or a worker's self-report; the
evidence is the `<report>.run.json` sidecar written by `run_worker.py`.

## Supported orchestration workflow

There is no user-selectable mode switch. Thin-root orchestration is the only
supported delegated workflow. Keep Fable focused on decisions where its judgment
has the highest leverage: architecture, acceptance criteria, material risk, and
final acceptance. After the contract is ready, DeepSeek owns repository discovery
needed within the brief, implementation, testing and debugging.

For a normal phase, target this root workflow: one planning batch, one dispatch
(one `run_worker.py` call), one wait, one batched acceptance review, and one
final response. Add Fable work only for a concrete blocker or an architecture,
security, or production-risk concern. Do not create root activity merely to
observe progress.

## 1. Orient and classify

Read the relevant repository guidance and current request. Preserve existing
work. Decide whether this is a direct small fix, a bounded build, or a large
multi-phase project. Keep trivial edits with Fable; do not force delegation onto
a typo or a simple question. For a substantial build, say what Fable will own
and what DeepSeek will implement.

Use the user's existing approvals and decisions. An explicit request to plan and
build authorizes the in-scope workflow; do not ask again after every phase. Ask
only about material unresolved product/risk decisions that cannot be established
from the repo. When asked to plan only, do not implement.

## 2. Confirm routing before delegating

Read `references/routing.md`. Run the read-only `scripts/doctor.py` once per
session (add `--check-api` the first time on a machine). It confirms a usable
Claude Code CLI, the presence of `DEEPSEEK_API_KEY` in the shell (never its
value), and the worker base URL. Its output is a static configuration check, not
an end-to-end model test. Never ask the user to paste the key into chat; if it is
missing, tell them to export it in the shell that launched this session and stop
delegation.

For a first routed task, use a small real, useful bundle and inspect the
`.run.json` afterward (`model_observed`, `base_url`, `usage`). No fake
model-name check and no silent fallback to Anthropic models for implementation.

## 3. Design before dividing the work

Read `references/planning.md`. Reuse an approved design/spec and phase plan when
one exists. For new work, produce an appropriately sized design covering
objective, non-goals, repo evidence, important alternatives, interfaces, failure
behavior, risks, and acceptance criteria. Fable makes architecture,
auth/security, tenancy, payments, secrets, and production-impacting decisions;
do not hand those to DeepSeek under a vague "build it" prompt.

## 4. Produce a phase plan and executable briefs

Default artifact home: `docs/agent-work/<feature>/` with `spec.md`,
`plan.json` (optional), `tasks/<ID>.md` briefs and `reports/<ID>.md` reports.
Follow an existing project convention instead when one is established.

Write a dependency-ordered phase plan. Prefer one coherent end-to-end vertical
bundle per phase when its contract is stable. Each brief (use
`templates/task-brief.md`) has exact contracts, a bounded file scope, testable
outcomes, and verification commands. Split tasks only at genuine dependency or
independent acceptance boundaries. If a machine-readable plan is useful, use
`templates/plan.json` and run
`scripts/validate_plan.py <plan.json> --repo-root <repository-root>` before
launch. That linter checks structure, not the quality of the design.

## 5. Dispatch and let the worker work

Read `references/execution.md`. Capture the workspace baseline first (branch,
HEAD, `git status --short`, untracked files). Then dispatch with one Bash call:

```
python skill-path/scripts/run_worker.py --task-id T1 \
  --brief docs/agent-work/<feature>/tasks/T1.md \
  --cwd <workspace> \
  --report docs/agent-work/<feature>/reports/T1.md \
  [--model deepseek-flash|deepseek-v4-pro] [--max-turns N] [--max-budget-usd X] [--timeout S]
```

Bound the run with `--max-turns` and `--timeout`. Avoid `--max-budget-usd` or set it
high: the CLI prices the run at Anthropic list prices, roughly 20-50x DeepSeek's, and
cache reads on a long bundle blow through a small cap mid-task (observed: a $3 cap
stopped a worker at 51 turns with the code done and the report unwritten).

Use a Bash timeout long enough for the whole bundle (up to the 600000 ms
maximum) or `run_in_background` and wait for the completion notification. Do not
poll the report file, read the stream log mid-run, or perform overlapping
repository work while the worker owns its paths. A timeout alone is not
evidence that the worker is stuck; check the `.run.json` and report.

The worker gets the full brief plus the bundled `worker-instructions.md`; it
runs in an isolated config directory with no access to this session's account,
hooks, skills or MCP servers, and cannot spawn agents. Default to ONE active
worker in the workspace. Use two only for independent tasks in verified separate
worktrees. No recursive agents.

For a correction cycle, resume the same worker session with the batched
findings instead of starting fresh:

```
python skill-path/scripts/run_worker.py --task-id T1 --brief <same brief> --cwd <workspace> \
  --report <same report> --resume <session_id from .run.json> --message "<all findings>"
```

## 6. Review the actual result

Read `references/review.md`. Worker completion means **ready for review**, not
accepted. Fable reviews the actual diff against the captured baseline,
including untracked files, in one batched pass with two lenses: specification
compliance, then code quality/security. Inspect the worker's evidence
(commands, exit codes) and spot-check where evidence is missing or a failure is
plausible. Do not routinely rerun the full suite. Accept only after both lenses
pass. Default to at most one correction cycle. Never silently switch the worker
to an Anthropic model to "finish it"; if DeepSeek cannot complete the bundle,
report that and let the user decide.

## 7. Integrate, checkpoint, and finish

Do not auto-commit, merge, push, deploy, or apply production migrations because
a phase finished. Update `CHECKPOINT.md` (see `templates/checkpoint.md`) at
resumable boundaries with accepted work, worker session ids, review status and
the exact resume action. Conclude with what was built, what actually passed,
outstanding limits, observed worker usage from `.run.json`, and the verified or
unverified routing state. Never estimate cost savings from task counts.

## High-assurance exception

Expand Fable's investigation, checks, or correction cycle only when evidence
shows material risk involving architecture, authentication/authorization,
payments, tenancy, secrets, destructive migrations, production behavior, or
high-impact shared infrastructure. State the reason for expanding the root loop.
