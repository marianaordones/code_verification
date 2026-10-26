# Solver Needs: two arms, 100 fixed tasks, 64k context

This is the full repair experiment, not another extraction pilot. It uses the same frozen `configs/solver-needs-tasks100.json`, the pinned Qwen2.5-Coder-14B-Instruct revision, the same initial failed candidates, seeds `20261018 + proposal_number`, and **three TOTAL proposals** per task/arm.

| Arm directory | Feedback |
|---|---|
| `without_internals` | Base24k / 50x3 + previous complement up to12k |
| `with_internals` | Exactly that shared package + advanced feedback up to14k |

Both arms receive internals. Directory names are retained for compatibility and explicitly explained in the reports. The shared complement retains the previous field types: up to20 input quantifiers without observed instances, input term examples, and per-quantifier counts. Its budget is now12k, not16k.

## Submit on the cluster

Update `baseline/`, `solver_needs_study/`, `diagnostics/`, `configs/`, `prompts/`, `scripts/`, and `tests/` (including fixtures). Updating `docs/` is optional. Do not update an active experiment's checkout: implementation/prompt hashes are frozen.

From `code_verification_git`:

```bash
bash scripts/submit_solver_needs_advanced64k.sh
```

The source defaults to the completed **original 24k/50x3** run:

```text
results/solver-needs-qwen14b-100-internals24k/seed-20261018
```

Do not substitute the later complement16k study: its source prompt/control protocol differs. Supply another source path if that original study was moved:

```bash
bash scripts/submit_solver_needs_advanced64k.sh \
  /home/mariana.soares/code_verification_git/results/solver-needs-qwen14b-100-internals24k/seed-20261018
```

Optional second argument sets a new output parent. Defaults:

```text
results/solver-needs-qwen14b-100-advanced64k/seed-20261018/
    shared-initial-events/
    study/
```

The launcher submits CPU preparation, a GPU job after successful preparation, and CPU comparison after the GPU job. Existing Slurm scripts use QoS `high`. Preparation is 2 CPUs /16G /4h; inference is one GPU /8 CPUs /64G host RAM /24h. No separate model-verification pilot is submitted. Both arms run in the same model session, alternating which arm goes first by task.

## Context and L40S

Both arms use **65,536 total tokens**, YaRN factor2 over32,768 positions, BF16, one active sequence, chunked prefill with a2,048-token batch, and4,096 tokens reserved for output.

| Part | Maximum tokens |
|---|---:|
| Base | 24,576 |
| Previous complement | 12,288 |
| Advanced block | 14,336 |
| Output | 4,096 |
| Nominal remaining program/instructions/diagnostics/history | 10,240 |

The runner tokenizes the **actual complete chat template** before every inference. The10k is a nominal allocation, not source truncation. When necessary only the advanced block is repacked smaller. Shared program/base/complement content is not cut to make room for advanced information. If the shared prompt cannot fit, that error is explicit. Context omissions, actual prompt counts, block token counts and headroom after the output reservation are saved.

For L40S capacity, the configuration explicitly requests `gpu_memory_utilization=0.95` in both arms; older experiments still default to0.90. This allocates more GPU memory for KV cache, without quantization or offloading. Actual GPU capacity is not guaranteed until initialization. Failure writes `study/initialization-error.json` and stops; there is **no silent context reduction, quantization, or CPU offload**. A100 GPUs may also run it, but resume must use the same GPU class recorded by the initial session.

## Initial evidence and subsequent repairs

Preparation validates the source manifest, frozen input hashes, candidate renderer, first-prompt provenance, and Verus/Z3 identities. It uses the same original100 IDs and initial candidate/query bytes; it does not rerun the initial Verus verification. Normal base/complement evidence is refreshed once in a shared pool using the previous collector, and the advanced collector is run on the same saved failing queries. The advanced collector uses capturev3 (isolated inventory, deferred AST formatting, native boundary marker), `combined`, five-second diagnostic timeout,64MiB trace cap and no enabled proof mode.

These are **separate diagnostic searches**: advanced events are not silently attributed to the original Verus search or the normal base replay. Only outcome-concordant replays with complete input inventory, valid trace boundary, zero callback/serialization errors and no trace-cap interruption are eligible. Failures/mismatches remain in metadata and raw files. At least one initial advanced package must be available before preparation succeeds.

The initial base/complement and selected advanced package are built **once per candidate**, frozen and hashed. Both first proposals share byte-identical common messages and feedback hashes; only the treatment receives the advanced block. After model actions diverge, each arm collects feedback for its own candidate. The control never runs the additional advanced collector during its subsequent repairs.

## Advanced package

The **14k cap is global per model request**, across up to three selected failing queries. It is not14k per query. Event IDs are qualified with query IDs, chains never cross queries, and clause deduplication retains query scope. Relevance is prioritized; tie ordering alternates queries so early queries do not automatically dominate.

- Up to12 matching explanations, preferred7k: triggers, actual matched terms, bindings and recorded equality explanations.
- Up to6 short chains, preferred4k: references to two/three events and their explicit term associations; no claim of necessary causality.
- Up to24 non-instantiation clauses, preferred3k: literals, original hint and available dependencies, including the limitations of generic `smt` hints.

Unused budget can be shared. Candidate costs/compact representations are cached; a final exact JSON measurement and whole-chat check enforce the budgets. Formulas are shared by hash within the advanced block. If an exactly identical formula already appears in the common base/complement, it is referenced there by block/query/index instead of repeated. Qid similarity alone is not enough for this deduplication. Missing/ambiguous associations and partial equality explanations retain their flags. No full SMT query is sent to the LLM.

The common interpretation guide is `prompts/solver-needs/advanced.txt`. Both arms see the same guide. The model returns the same four-field localized action as before; executable implementation and contracts remain protected by the existing renderer and Verus checks. Published category labels, removed assertions, and successful probes remain hidden from the LLM.

## Results and resuming

Read `study/comparison.md` and `comparison.json`. They include cumulative success by proposal, categories, exclusive wins, first-pair checks, missing tasks and advanced-exposure counts. Inspect `inputs/ID/feedback.json`, per-attempt `request.json`, `exposure.json` and `advanced-selection.json` for actual messages, omission reasons and budgets. Per-query `advanced/QUERY/` retains process reports, availability, traces, parsed evidence, inventory and clauses.

Re-submit only the inference job to resume saved tasks, with the same code, prepared study and GPU class:

```bash
sbatch scripts/slurm/solver_needs_run.slurm \
  results/solver-needs-qwen14b-100-advanced64k/seed-20261018/study
```

Preparation snapshots and per-attempt results/requests prevent silently mixing different configurations. A failed or unchanged proposal counts toward the three-proposal budget. Already verified initial candidates are not credited as model repairs. Do not edit manifests to bypass hash errors.
