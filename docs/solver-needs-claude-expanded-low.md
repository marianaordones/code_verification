# Expanded exploratory run: 60 additional IDs, Low effort

Configuration: `configs/solver-needs-claude-low.json`. Only effort (`low`) and
experiment name differ from the Medium pilot. Three proposals per task/arm,
Opus 5.5, unchanged input/feedback budgets and extraction `single-json-action-v2`.

Selection: `configs/solver-needs-claude-expanded60.json`, ten IDs per category,
excluding V-135, V-411, V-381, V-245, V-56 and V-22. Programs are preferentially
diversified: 54 unique source files. Repeated programs and development-source
overlap are recorded. The deterministic selector reads benchmark metadata only,
never Qwen or Claude outcomes. Regenerate only to a NEW path with
`python -m solver_needs_study.select_claude_pilot --output NEW_PATH`.

This is an exploratory expanded sample, not 60 independent programs or a
confirmatory comparison with the earlier six Medium tasks. Changing both sample
and effort prevents attributing any difference against that pilot to effort.
The primary comparison is with versus without internals within Low on these IDs.
For comparison to Qwen, use exactly these IDs and restrict it to three proposals.

Run in the WSL project:

```bash
bash scripts/run_claude_expanded_low.sh prepare
bash scripts/run_claude_expanded_low.sh run
bash scripts/run_claude_expanded_low.sh compare
```

Study: `results/claude-local-expanded60-low-v2`. At most 360 requests; stop each
trajectory after success. Quota/transport errors stop the entire run. Completed
responses are reused; ambiguous/failed CLI receipts require explicit inspection
before resubmission. Do not update CLI/code/config while resuming the same study.
This does not buy API credits or enable extra paid usage. Keep extra paid usage
disabled in the Claude account to stop at included subscription limits.

Preserve the original code for older prepared studies: implementation hashes
change when adding the selector and enabling Low. Old results must not be resumed
with the new source checkout. The expanded preparation freezes the new checkout.
