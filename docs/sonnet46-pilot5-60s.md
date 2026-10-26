# Sonnet 4.6 Low: five pending tasks, 60 seconds per proposal

Fixed selection, before any new model requests: misc_conditional_average,
misc_fib, misc_filter, misc_findmax, misc_len_intersect. These are the next five
pending tasks in original order, excluding misc_bubble already evaluated in the
180-second pilot. This is a small exploratory convenience sample from the misc
subset, not a representative sample of VerusBench.

Unchanged: model/Low effort, prompt, original verifier/Lynette, shared initial
proposal without internals, up to two repair proposals per arm, 14,336-Qwen-token
internals packet, 50 quantifier groups x 3 instances. New policy: 60 seconds per
model call and 8192 output tokens including thinking; no automatic continuation.
Local cancellation cannot guarantee zero server-side overshoot. Resource stops
consume proposals and are counted separately from rejected/invalid proposals.

Output: `results/verusbench-sonnet46-pilot5-60s-v1/pilot-summary.md` and JSON.
Original results are preserved. No automatic merge into the original 50-task
report. The copied manifest still covers the original 50 frozen inputs; the
pilot-plan.json and pilot-summary files define and summarize only these five.
New transport and pilot driver hashes are frozen in pilot-plan.json.

```bash
cd ~/projects/code_verification
# Once only; already performed during initial setup:
bash scripts/run_sonnet46_pilot5_60s.sh prepare
# Runs/resumes only this fixed pilot; do not run concurrently:
bash scripts/run_sonnet46_pilot5_60s.sh run
# After run exits:
bash scripts/run_sonnet46_pilot5_60s.sh status
cat results/verusbench-sonnet46-pilot5-60s-v1/pilot-summary.md
```

At most 25 unique calls; shared successes avoid all four repair calls. The
original-position alternating arm order is preserved. Normal saved responses
and results are reused. Incomplete receipts block a new request until inspected.
Authentication/quota/infrastructure failures stop the pilot without retrying.

For progress during execution, read the live stdout terminal or existing
pilot-summary.md (updated between tasks). The status command takes the run lock
and therefore should be used after the executor has stopped.

Offline checks:
`python -m unittest tests.test_claude_bounded tests.test_sonnet46_pilot5_60s`
