# Sonnet 5.5 Low: twenty additional VerusBench programs

Same proof-completion protocol as the five-problem Sonnet run: original unverified
programs, full-file output, Low effort, three total proposals per program per arm,
with/without internals, Verus plus Lynette acceptance. Maximum 120 model requests.
No changes to prompts, feedback budget, toolchain, extraction or action space.

Configuration: `configs/verusbench-sonnet20-v2.json`. Frozen IDs and source hashes:
`configs/verusbench-sonnet20-selection-v2.json`. Five programs per category
(CloverBench, Diffy, MBPP, Misc), selected by deterministic category round-robin
and shuffled ID-sorted pools, seed 20261024. The five previous IDs and identical
original file contents are excluded. No model outcomes used. Selection is fixed
before verification; initially verifying originals are reported, not replaced.
This is a balanced exploratory sample, not a category-proportional benchmark rate.

The new batch needs fresh preparation because these are twenty NEW problems.
`VB_SOURCE_STUDY` is explicitly unset by the wrapper. Each pair starts with the
same frozen initial source and diagnostics. Later trajectories may differ.

In WSL (new code and configurations must be synced first):

```bash
cd ~/projects/code_verification
bash scripts/run_verusbench_sonnet20.sh prepare
bash scripts/run_verusbench_sonnet20.sh run
cat results/verusbench-sonnet20-low-v2/comparison.md
```

Preparation runs Verus/Z3 but never calls Claude. Run sends real requests via the
native subscription login. No installation or toolchain rebuild is necessary.
Keep extra paid usage disabled. Transport/quota errors stop the batch; responses
and completed proposals are saved, and ambiguous CLI calls are not automatically
resubmitted. Do not update CLI/code during preparation or execution.

Prior results remain in their original directories. The old source snapshot is
preserved before syncing this generalized runner, since implementation hashes
prevent resuming old studies with changed code. Denominators and completion checks
now use the actual selection size rather than a hard-coded five.

## Original-policy screening (v2)

The initial v1 preparation stopped on `misc_havoc_inline_post` because that
benchmark original contains two `assume` calls. Verus executed normally; the
integrity policy rejects these even in the original. The v2 selection applies
the existing lexical guard to each original BEFORE randomized selection and
records exclusions in `screened_out_originals`. Only this original was excluded
from the 150-input inventory. Nothing is removed from any program, and the
integrity policy is not relaxed. Twenty eligible programs are fixed, still
five per category and excluding the previous five. This narrows the study to
original inputs compatible with the existing trust policy, not all VerusBench.
The v1 preparation remains intact; do not resume it using the v2 code.
