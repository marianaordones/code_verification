# Sonnet Low: common first proposal, paired proposals 2 and 3

The initial generation is made ONCE without internals, saved under
`shared/ID/attempt_01/`, and reused as the start of both repair arms. This is not
two calls with equal seeds. Model is Sonnet 5.5, effort Low, no seed/temperature
control. Every raw input already verifying is excluded from model repair and
reported separately. First-generation successes are common successes, not credited
as repaired by either arm. No replacement problems are selected after outcomes.

If generation 1 fails (including invalid output), freeze its candidate, diagnostics,
integrity result, response, result and one diagnostic internals package. Both arms
receive the identical original, failed candidate, conventional diagnostics and
attempt history at proposal 2. Only treatment receives internals. The request
hashes and `shared-state.json` audit this fork. Proposal 3 follows each arm's own
proposal-2 candidate/diagnostics, so trajectories can diverge. Overall effect is
the effect of adding feedback during this two-repair policy, not an isolated
effect at proposal 3 on identical inputs.

Selection: `configs/verusbench-shared20-selection.json`, twenty new problems,
excluding all 25 previously tested IDs and identical original contents. Existing
lexical screening removes benchmark assumptions incompatible with the policy.
Only four eligible CloverBench inputs remain, hence 4 CloverBench, 6 Diffy,
5 MBPP and 5 Misc. Fixed category round-robin; no model outcomes read.

All previous action-space, whole-file output, Verus/Lynette, prompt, replay and
budget choices remain. Known input LexErrors are automatically counted as invalid
only after whole-file Verus also rejects them; arbitrary checker errors still
stop. Quota/timeout calls are not automatically resubmitted. No extra formatting
repair calls or accepting source without integrity checks. Raw errors preserved.

Preparation reuses the established original-input verifier and captures initial
diagnostics; the initial internals package it computes is NOT sent to generation 1.
After a failed shared generation, a fresh package is produced for that actual
candidate. The new runner's source hashes are additionally frozen in the manifest.
Previous experiment source files are unchanged.

```bash
cd ~/projects/code_verification
bash scripts/run_verusbench_shared20.sh prepare
bash scripts/run_verusbench_shared20.sh run
cat results/verusbench-shared20-sonnet-low-v1/comparison.md
```

No new dependencies or toolchain build. Preparation never calls the model. Run
uses native Pro login, tools disabled, and at most 100 requests: 20 shared first
proposals plus 2 arms x 2 repairs x 20 shared failures. If most initial proposals
succeed, the repair denominator will be small or zero; this is reported, not
silently expanded to 20 failures. Keep extra paid usage disabled.

Report separately: already-verifying originals, successes of the shared proposal,
repair denominator, exclusive successes at proposal 2 and proposal 3, cumulative
repairs, fork validity and completion. Rates of repair should use only common
failed candidates. CLI/runtime and frozen input hashes must match on resumption.
