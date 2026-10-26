# Sonnet 4.6 Low: exact 50-problem subset, 14k feedback, 50x3

`configs/verusbench-sonnet46-50-selection.json` fixes all fifty user-supplied
VerusBench IDs, in the supplied order, with original source SHA-256 hashes.
7 CloverBench, 15 Diffy, 14 MBPP, 14 Misc. No random sampling, outcome selection,
or replacement. Some programs were used in previous studies; this is an
exploratory user-selected subset. The input is the original UNVERIFIED source,
not a Qwen candidate or a verified reference. Already-verifying inputs receive
no model calls and are reported separately, never silently replaced.

## Frozen protocol

- Model ID `claude-sonnet-4-6` (no alias and no `[1m]` suffix), explicit Low.
- One first proposal generated ONCE without internals, saved under `shared/`.
- Initial successes are reported separately. Failed shared candidates are frozen
  with original response, diagnostics, integrity result, history and one replay
  packet. Proposals 2 and 3 start from that SAME state in both arms; only treatment
  receives internals. Proposal-2 common/candidate/checkpoint hashes must match.
- Each third proposal follows its own branch's second failure. The effect measured
  is adding internals to this two-repair policy, not a third-proposal comparison
  on guaranteed identical candidates.
- Full-file proof completion. Verus and the existing Lynette/lexical preservation
  checks must both pass. Original implementation, contracts/imports remain fixed.
  No catalogue insertion, explicit NLA switch, tools or retrieval are added.
- At most one captured SAT/UNKNOWN query is replayed for five diagnostic seconds,
  with a twenty-second outer worker limit. Expose data only on matching outcome.
- At most 50 quantifier groups and 3 instances per group. Reuse the existing
  worker, relevance ranking, diversity-first selection and background quotas.
  The worker's internal reservoir retains up to 128 groups; it is not all sent.
- Internals budget **14,336 = 14 x 1024 tokens**, measured by the pinned Qwen
  tokenizer INCLUDING the solver_internals wrapper. Prompt envelope remains
  49,152 Qwen tokens including 4,096 reserved for output. These are NOT Claude
  token counts; output reserve is NOT a hard output cap. Seed/temperature are null.
- No truncation of original source/diagnostics. Packet caps may not fill. Actual
  availability, group/instance counts and Qwen token count are in `exposure.json`.
- Invalid/empty/unchanged output consumes a proposal. Known Lynette input LexError
  or `Syn unable to parse file` is counted as invalid only when Verus also confirms
  compilation failure; raw errors are preserved. Arbitrary panics, timeouts,
  quota, unavailable model, or toolchain/runtime changes stop the study.

Maximum 250 requests: 50 common first proposals plus two arms x two repairs x
50 shared failures. If most first proposals succeed, the repair denominator may
be small. We do not add problems to force a denominator of fifty failures.

## Execution in WSL

The runner is isolated from previous studies; source files for prior experiment
pipelines are unchanged. Existing native VerusBench tools/dependencies are reused:
Verus 33269ac, Z3 4.12.5, patched Lynette. No new toolchain build or model weights.

```bash
cd ~/projects/code_verification
bash scripts/run_verusbench_sonnet46_50.sh prepare
bash scripts/run_verusbench_sonnet46_50.sh run
cat results/verusbench-sonnet46-low-shared50-14k-50x3-v1/comparison.md
```

Preparation never calls Claude. The run uses the official native Pro login with
tools/customizations disabled, transcript model checks, and no automatic
transport retry. Keep extra paid usage disabled. The exact model must be available
to the account; no fallback to Sonnet 5.5 is accepted. No 1M-context variant is
requested. Do not update CLI/code during a study. Repeat `run` to reuse completed
responses/proposals; ambiguous interrupted CLI receipts need inspection before
explicit resubmission. `compare` updates the report without model calls.
