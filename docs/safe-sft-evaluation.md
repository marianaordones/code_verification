# Evaluation of the SAFE-enriched adapter

These are two new evaluations of the trained adapter: all 150 VerusBench tasks
and all 462 Solver Needs Verus/Z3 missing-assertion tasks. Each has two arms:
without_internals and with_internals. There is no untrained-model arm. Both arms
load the same trained rank-16 adapter on the pinned BF16 base model through vLLM's
LoRARequest on every generation. The training-time 4-bit quantization is not the
inference format; inference uses BF16 base weights plus the learned adapter.

## Submit

Update the repository. Keep the adapter and original training data on the cluster.
The defaults are results/safe-sft-a100-v1/adapter and data/safe/sft-enriched-v1.
The training-provenance.json alongside adapter/ is required. Submit both datasets:

```bash
SFT_GPU_TYPE=L40S bash scripts/submit_safe_sft_eval.sh all
```

Or use SFT_GPU_TYPE=A100; exact types match the cluster's sinfo output. No node
specification is used. Each dataset submits one CPU prepare, one dependent GPU
run, and one report after the GPU job ends. The two GPU jobs can run concurrently
on two separate GPUs; each loads the model once for both feedback arms.
GPU defaults: high_performance / high, 64G host RAM, 48h. CPU defaults:
new_p_general / high, held submission then configured exclusions, as for collection.
SAFE_EXCLUDE_NODES can override exclusions. Installation and staging use existing
native caches; no new source builds, finetuning or adapter merging.

Submit only one dataset, or change adapter/output parent:

```bash
SFT_GPU_TYPE=A100 bash scripts/submit_safe_sft_eval.sh solver-needs \
  results/safe-sft-a100-v1/adapter results/safe-sft-eval-v1
```

Submission IDs are printed and saved to logs/safe-sft-eval-submission-*.tsv.
Outputs: results/safe-sft-eval-v1/{verusbench,solver-needs}/comparison.md and
comparison.json, plus frozen manifest, task IDs, adapter hashes, training-overlap
screening, requests, responses, candidate files, preservation, Verus diagnostics,
captured queries and replay/selection records. The model is never sent full SMT
queries or the removed assertion, category label, teacher response or known probe.

## Task policy

Three TOTAL proposals per task and arm. Responses are complete Verus files,
matching the SAFE SFT targets, rather than the historical Solver Needs JSON actions
or the VerusBench localized-edit format. Temperature .7, top_p .8, top_k 20,
output 4096, seeds matched per task/proposal between arms.

VerusBench: generate the same first proposal once, using the initial program and
Verus diagnostics without internals. Both arms inherit that exact proposal; up to
two subsequent repairs differ only by solver feedback. This is a new generation
run of the trained model, not reuse of untrained Qwen's old failed candidates.

Solver Needs: both start from the same assertion-removed program. The with arm
receives initial failing-candidate internals before proposal 1. The control gets
the same program, diagnostics and interpretation instructions but no internal
payload. Any initially verified cases are reported separately, not model repairs.

Full files must preserve executable implementation and requires/ensures. The
SAFE attribute policy permits loop_isolation(false) and proof trigger changes,
but not assume/admit, trusted bypasses or added executable empty infinite loops.
Integrity is checked against the original task, not just the previous repair.
Rejected edits leave the previous state intact and supply a dedicated rejection
message next time. Valid edits with failed verification become the next state.
Syntax/unparseable/checker errors are counted separately from prohibited edits.
An identity-preservation audit of each original input is saved in baseline-integrity;
its failures reveal parser/checker limitations and must not be presented as inability
of the model to prove the corresponding tasks.

Solver Needs uses the pinned 2026 Verus release, rlimit 10, crate-type lib,
no-auto-recommends-check and its bundled Z3. VerusBench uses historical Verus
33269ac and bundled Z3. This evaluator keeps global solver settings fixed; the
model can add source-level checked nonlinear_arith proofs, reveal_with_fuel,
assertions, invariants and proof helpers. It does NOT offer the historical JSON
NLA toggle or checked AX catalogue actions. Therefore the arms are directly
comparable within this evaluation; comparisons to old action-based experiments
also reflect a change of repair interface.

## Feedback and context

32,768 total context, matching the training range; 4,096 output reservation.
Base package only: up to 24,576 tokens, 50 quantifier groups, 3 instances/group,
7 selected statistics and associated raw callback terms/clause literals. No extra
complement/matching/dependency blocks. The same source-relevance ranking and
background quotas used in SAFE collection apply. Up to the first 3 failing
SAT/UNKNOWN captured queries; 5s diagnostic checks and 20s wall / 2GiB replay
limits; raw reservoir 128 groups x 8 saved instances. Only outcome-concordant
diagnostic replays contribute. These are NOT the original solver's search.

The 24k and 50x3 limits are ceilings, not a guarantee of that much feedback in
every request. Selection also respects remaining total context. No truncation of
programs or diagnostics. If even the no-internals prompt cannot fit, the attempt
is explicitly recorded as context_budget. A statistics-only packet that cannot
fit is omitted with packet-omission.json, not silently clipped.

## Reporting, overlap and resume

The final training loss is not proof accuracy. Only actual Verus success plus
valid preservation counts as a repaired proof. Curves through proposals 1/2/3,
category totals, exclusive wins, unchanged outputs, truncation and gate errors
are reported. Shared VerusBench proposal costs are included in both arms for
comparison but were physically executed once. Missing tasks are visible.

Preparation checks the actual training JSONL IDs and original SAFE dataset SHA,
then screens their source and target against the evaluated inputs using token
equality and >=80% containment of 12-token benchmark shingles. Flags, including
Solver Needs flags not screened before training, are saved. Reports retain all
tasks and provide an unflagged subtotal/denominator. A flag is not proven leakage;
an unflagged task is not certified independent, especially after identifier or
structural changes. Review this before making generalization claims.

Resume by submitting the same dataset and parent again. Completed tasks and saved
responses are reused; changed input/adapter/code/tool identities block the run.
Do not update shared code while jobs are prepared/queued/running. Reporting can
also be submitted without new inference, using the CPU report script and output:

```bash
sbatch scripts/slurm/safe_sft_eval_report.slurm \
  --output results/safe-sft-eval-v1/verusbench
```

Local tests cover shared-first behavior, matched seeds, exposure timing, pending
tasks, smoke-adapter rejection and no repeated inference on resume. Actual LoRA
inference, native preservation compatibility and GPU feasibility require the
cluster; no evaluation success numbers have been produced locally.

If Solver Needs initialization fails with `rustup: Invalid argument` on HOME,
update scripts/cluster/stage_solver_needs.sh and stage_local_rustup.sh. The helper
copies rustup to the executable native scratch directory, preserves the selected
runtime's PATH and keeps the shared Rust installation/toolchains unchanged.
Resubmit only solver-needs with the same output parent. Completed preparation and
responses are reused; no finetuning is repeated. If rustc itself subsequently
fails from a shared path, that is a separate toolchain staging issue: inspect its
exact path/error before reinstalling or changing Rust versions.
