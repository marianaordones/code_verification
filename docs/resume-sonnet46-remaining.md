# Resume the twelve remaining Sonnet 4.6 tasks

The original 50-case study remains unchanged. Current pending IDs:
misc_bubble, misc_conditional_average, misc_fib, misc_filter, misc_findmax,
misc_len_intersect, misc_linearsearch, misc_map, misc_remove_all_greater,
misc_reverse, misc_sum, misc_tail_triangle.

```bash
cd ~/projects/code_verification
bash scripts/resume_sonnet46_remaining.sh check
bash scripts/resume_sonnet46_remaining.sh run --retry-interrupted
```

`check` is read-only, does not call the model, and reports the current pending
selection and incomplete CLI receipts. `run` processes ONLY unfinished tasks,
in their original positions (preserving alternating arm order). It does not
regenerate the 38 completed tasks, alter the selection or rerun preparation.
Same Sonnet 4.6 Low, shared first generation, two repairs per arm, 14k/50x3.
The original whole-study report is updated, including all 50 cases.

The first call for misc_bubble has state started and no saved response. Its prior
usage/output is unknown; it may have consumed subscription usage. The flag
`--retry-interrupted` explicitly authorizes resubmitting the identical saved
request. The receipt and any empty stdout/stderr files are moved into a unique
`interrupted-calls/` archive within the attempt; request.json is never deleted
or altered. This is an audited transport resubmission, not a hidden free call.
It can entail extra usage beyond the nominal proposal count for that interrupted
request. A nonempty raw stream requires separate inspection instead of automatic
resubmission. Existing response.json or successful saved streams are reused.

The script verifies the original code/input hashes, tools and runtime BEFORE
archiving an interrupted receipt. An existing run lock prevents overlap. Quota,
timeouts and subsequent failures still stop; there is no automatic retry loop.
If the runtime changed, do not bypass the check. Keep extra paid usage disabled.
Up to 60 NEW requests for the twelve pending tasks, with early stopping.

Results: results/verusbench-sonnet46-low-shared50-14k-50x3-v1/comparison.md.
No new study folder or model selection in the interactive menu is required.
