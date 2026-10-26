# Saved-call investigation — 2026-10-26

No inference requests were made during this investigation. Existing experiment
packages, configurations, manifests and results were not changed.

Study: `results/verusbench-sonnet46-low-shared50-14k-50x3-v1` in WSL.

## Findings

- `shared/misc_bubble/attempt_01/claude-call.json`: timed_out after
  900.022490583 seconds, return code -9, Sonnet 4.6, explicit low effort.
- Saved stream: one init/session, no tools or MCP, two automatic user messages
  saying the output limit was hit and requesting continuation, no final result.
  Assistant blocks contain redacted thinking and no recoverable source text.
- Thinking progress counters reset between those continuations. Segment peaks:
  31,950; 31,850; 13,200. Their sum is approximately 77,000 estimated thinking
  tokens, NOT a final billing or usage counter. The earlier 13,200 figure covered
  only the last segment.
- Saved rate-limit events report five-hour utilization 1% then 14%, with the
  same reset time; there is no final event to verify the user's observed 30%.
  Both report isUsingOverage=false and org_level_disabled for overage.
- Two archived started receipts show earlier interrupted starts of the same
  request. They have no saved streams, so their consumption cannot be measured.
  These are distinct from the current CLI's automatic continuation messages.
- Process inspection found no active Claude or experiment Python process.
- 88 completed receipts: median duration approximately 12.24 seconds. A prior
  with-internals mbpp_task_id_798 proposal 3 lasted 546.50 seconds and its final
  usage reports 37,157 output tokens, including 36,138 thinking tokens.

## Implementation gaps

`max_tokens=4096` is used to reserve prompt context, but the CLI transport never
sets an output-token limit from it. `effort=low` is not a hard token budget.
`--max-turns 1` did not prevent the observed output-limit continuation behavior.
`CLAUDE_CODE_MAX_RETRIES=0` concerns failed-request retries and did not prevent
these continuations. The environment scrubber removes caller-supplied
CLAUDE_* and MAX_THINKING_TOKENS overrides, so exporting a budget in the shell
does not fix this runner.

`communicate()` buffers output until process completion or timeout. Therefore
there is no live audit/progress or early cutoff based on stream events.

## Recommended next change (not implemented here)

Do not increase the timeout as the first response. Implement explicit output
budget configuration using documented CLI controls, immediate stream logging,
progress reporting, a conservative elapsed-time cutoff, and termination on
automatic continuation events. Validate those controls with mocked streams
before any new model request. A per-request output limit alone must not be
described as a total multi-request budget. Record a new execution protocol
version rather than silently mixing changed resource limits with frozen runs.

References:
- https://code.claude.com/docs/en/env-vars
- https://code.claude.com/docs/en/model-config
- https://code.claude.com/docs/en/cli-reference

Read-only audit helper: `scripts/audit_sonnet46_calls.py STUDY_DIRECTORY`.
