# Remaining six tasks plus misc_filter: 120 seconds

Fixed IDs: misc_filter, misc_linearsearch, misc_map, misc_remove_all_greater,
misc_reverse, misc_sum, misc_tail_triangle.

This includes six tasks not evaluated in the bounded pilots and a fresh full
rerun of misc_filter. misc_bubble was already evaluated separately and is not
repeated. The five-task 60-second results and the original study are preserved.
misc_filter starts from the original unverified program again: no failed
60-second responses or shared candidates are carried over. This is a fresh run,
not a controlled same-first-candidate comparison of the two timeouts.

Sonnet 4.6 Low; one shared initial proposal without internals, followed by up to
two repairs per arm after failure. Each trajectory has three proposals. At most
35 model calls for seven tasks. Model inference timeout: 120 seconds per call.
Output limit remains 8192 tokens including thinking; internals remain 14336
Qwen tokens, 50 groups x 3 instances. The transport stops on automatic
continuation events and records resource exhaustion separately. Local stopping
cannot guarantee zero server-side overshoot. The timeout does not guarantee a
maximum percentage of Pro usage. Verification/replay have separate timeouts.

Run from WSL:

```bash
cd ~/projects/code_verification
# Once only, if not already prepared:
bash scripts/run_sonnet46_remaining7_120s.sh prepare
# Makes Claude requests; start only when ready:
bash scripts/run_sonnet46_remaining7_120s.sh run
# After it stops:
bash scripts/run_sonnet46_remaining7_120s.sh status
cat results/verusbench-sonnet46-remaining7-120s-v1/pilot-summary.md
```

Prepared output:
`results/verusbench-sonnet46-remaining7-120s-v1`.
The new plan freezes selection, policy and driver/transport hashes. The original
manifest and input checks remain in effect. The copied manifest lists all 50
original inputs, but only the seven fixed IDs execute. Use pilot-summary.json/md
for this batch. Results are not automatically merged into the original report.

Completed responses/results are reused when running the same command again;
an incomplete receipt without response blocks resubmission until inspected.
Authentication/quota/infrastructure failures stop the batch without retries.
Do not run a second executor concurrently; status also takes the run lock.

Offline tests (no provider requests):
`python -m unittest tests.test_claude_bounded tests.test_sonnet46_remaining7_120s`
