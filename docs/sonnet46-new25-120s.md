# New 25-ID VerusBench study

Exact user selection in supplied order, checked against the pinned 150-task
inventory and required to be disjoint from the previous 50-ID selection. This
does not assert that no ID was ever used in an older experiment outside those
50. No silent replacements on unknown IDs or initial verifier/integrity errors.

Sonnet 4.6 Low; one shared first proposal without internals, then at most two
repairs per arm. Same full-file proof completion, Verus and Lynette acceptance,
prompts and diagnostic selection as previous bounded batches. Internals:
14,336 Qwen tokens, 50 groups x 3 instances, one replay query. Output: 8192
tokens including thinking; 120 seconds per proposal; local cancellation on CLI
automatic continuation. Resource stops consume a proposal and are reported
separately from invalid/rejected proposals. Local cancellation does not promise
zero server overshoot or a fixed percentage of Pro quota.

```bash
cd ~/projects/code_verification
bash scripts/run_sonnet46_new25_120s.sh prepare
bash scripts/run_sonnet46_new25_120s.sh run
cat results/verusbench-sonnet46-new25-120s-v1/pilot-summary.md
```

Preparation verifies original inputs locally and checks Claude version/auth,
but sends no inference requests. If already prepared, prepare validates and
returns. It never overwrites an incompatible plan. Run makes at most 125 unique
model calls; shared first successes avoid all repair calls. Source inputs and
new transport/driver/study code hashes are frozen in the plan. Completed
responses/results are reused on rerun; incomplete receipts block resubmission.
Quota/authentication/infrastructure errors stop rather than retry. Do not start
multiple executors concurrently. The status command acquires the run lock, so
use it only after the executor stops:
`bash scripts/run_sonnet46_new25_120s.sh status`.

The new directory has its own 25-task manifest and pilot-summary.json/md.
Initially verified cases are excluded from model-repair outcomes. Shared first
successes count toward final solved programs in both arms, and are separately
identified so they are not credited as repairs. Old experiments stay unchanged.

Offline checks:
`python -m unittest tests.test_claude_bounded tests.test_sonnet46_new25_120s`
