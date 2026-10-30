# SAFE: CPU pilot with 200 repair examples

This collects data only. No GPU, Qwen inference, fine-tuning, or LLM service is used. It downloads only the pinned Qwen Coder tokenizer files.

## Run on the cluster

Finish other jobs using this checkout before updating it: the shared feedback implementation participates in existing study fingerprints. Update `safe_internals/`, `solver_needs_study/`, `configs/`, `prompts/`, `scripts/`, `tests/`, and the new root file `requirements-safe-cpu.txt` (or update the whole repository).

Copy your original **sft_safe_25k (1).json** into `data/safe/sft_safe_25k.json` on the cluster. The destination filename may change; its bytes must remain unchanged. From the cluster repository root:

```bash
mkdir -p data/safe
# Copy the SAFE JSON into that directory using your usual file transfer tool.
bash scripts/submit_safe_internals_pilot.sh
```

If it is already elsewhere, do not copy it again; pass its path (quote spaces):

```bash
bash scripts/submit_safe_internals_pilot.sh "/existing/path/sft_safe_25k (1).json"
```

An optional second argument changes the output directory. The default is `results/safe-internals-pilot200/seed-20261018`. A single job requests **4 CPUs, 32G host RAM, 24 hours, high QoS, no GPU**, processing two examples concurrently. The job builds a separate small CPU Python cache; it does not use `setup_runtime.sh` or install vLLM/PyTorch.

It reuses the existing native VerusBench tools bundle. The usual sibling `code_verification/.cluster` fallback works. If needed, set this before submission:

```bash
export VERUSBENCH_TOOLS_DIR=/home/mariana.soares/code_verification/.cluster
bash scripts/submit_safe_internals_pilot.sh
```

No native tools bundle? This pilot does not build Verus; restore/provide the existing bundle first. It must contain `tools-native.json` and `tools-native.tar.gz`. Do not substitute the newer Solver Needs Verus release.

The CPU job adds the existing cargo/rustup directories to PATH before staging Verus and checks Rust 1.76.0. If missing, it installs that toolchain without self-updating rustup or changing the default toolchain. A tokenizer-only warning about missing PyTorch/TensorFlow/Flax is expected. pip warnings mentioning unrelated system packages such as Streamlit/s3fs do not establish a collector failure: the pilot installs into its own cache; new installations ignore globally installed packages.

Logs: `logs/safe-internals-200-JOBID.out` and `.err`. The `.out` prints `Collected safe-NNNNN: STATUS` once an example finishes. No real collection has been run locally during implementation.

## Selection and provenance

`configs/safe-repair-pilot200.json` freezes 200 IDs, original zero-based row indices, input code hashes and diagnostic strata. The selection is deterministic (seed 20261018), contains unique input programs, and round-robins historical diagnostic categories and presence/absence of input `loop_isolation(false)`. It is deliberately diverse, not a representative random estimate of the whole SAFE distribution.

Original JSON: 24,828 rows, including 13,768 repair rows, SHA256 `91e10c33b82a321bb64782baee96ab1ffc6c78b406fc30ab22f2b2ab10e7637e`. A different file fails explicitly instead of silently selecting another pilot. No target text, successful target execution, target difference or target label ranks the feedback. All original fields survive in `original.json` and `master.jsonl`.

The first Rust input fence is the candidate. The second is only a historical diagnostic snippet and is never concatenated to the program. The output fence is the reference solution. Fresh Verus diagnostics replace historical diagnostic text in **all exported views**, with the original text retained in the master. Common system guidance is identical across the three views.

Exact input/output hashes and available origin labels form conservative family components over the whole source file before expansion. These are metadata only, not model input. **No train/validation/test split is produced**: exact matching does not establish semantic independence or lack of VerusBench/Solver Needs overlap. This pilot is not ready for training without further filtering/splitting.

## Tools and compatibility

Uses the existing historical VerusBench Verus revision **33269ac** and its native Z3; the API replay uses isolated **z3-solver 4.12.5.0**. Their identities, tokenizer revision/files, resolved CPU dependencies and collector implementation are saved. Resuming with another binary/library/tokenizer/configuration is rejected.

The original SAFE Verus commit was not established from the publication/data card consulted. This is an explicit compatibility pilot, not a claim to reproduce the original SAFE verifier. Input and target compilation/verification failures remain visible; do not silently migrate their code or assume every historical target verifies on this version.

## Per-example collection

1. Execute the unmodified input with Verus, transparently capture original Z3 stdin/stdout, and save individual SMT queries/outcomes. Input `loop_isolation(false)` is left in place; an attribute appearing only in the target is never transferred to the input.
2. For a failed input, replay the first up to three SAT/UNKNOWN queries once each. Each replay has a 5-second solver timeout, 20-second outer wall limit and 2GiB per-process address-space limit. Verus processes have 120 seconds and a 4GiB per-process address-space limit. Child processes inherit a 128MiB **per-file** size limit; this is not a total-directory storage quota. Resource/capture failures remain recorded and may prevent feedback.
3. Save the existing relevance-ranked reservoir: up to 128 quantifier groups per replay, up to eight distinct instances per group, with events above 64,000 serialized characters omitted. Counts of observed/saved events and callback errors remain in raw reports. These are bounded samples, **not all quantifiers or all events in the search**. No matching/chain/clause-complement collection is added.
4. Build both views from those same saved events, without a second replay: **12,288 tokens / 20 groups × 3 instances**, and **24,576 tokens / 50 groups × 3 instances**. Ranking, background quotas and whole-formula selection reuse the existing selector. Limits are global across selected queries. Only result-concordant replays are eligible. Arithmetic-statistic key spelling is normalized; original statistics remain in the replay report.
5. Verify the original output separately, after feedback selection. Run preservation independently, allowing only added `loop_isolation(false)` attributes in a comparison copy. The actual target verified by Verus is never stripped or edited. Other preservation failures are recorded, not discarded.

Inputs that already verify, compilation/syntax failures, no captured failing queries, divergent replays, targets that fail, and targets containing actual `assume(...)` calls all remain in the master. `assume` is tagged independently on input and target, ignoring comments and strings; nothing is filtered yet. An accepted target containing `assume` is not thereby certified as a complete proof. Verifier infrastructure failures stay pending for retry.

## What the LLM-facing package contains

No complete SMT query is sent. The payload contains replay scope and query identity/hash, original/replay result, replay unknown reason and limit, seven selected statistics, complete sampled quantified formulas, raw callback-order substitution terms and associated clause literals. Formulas retain their SMT qids/patterns when present. No source-variable correspondence is guessed.

The shared prompt `prompts/safe-internals.txt` explains each counter, replay limitations, incomplete sampling, how formulas/terms can suggest proof hints, and cast/index pitfalls. It requests a complete corrected Verus file, matching SAFE's original target format, not the localized Solver Needs JSON action or its law catalogue.

Each candidate packet must fit its own budget and a 61,440-token collection prompt with 4,096 output tokens reserved. This is a packaging ceiling, **not a chosen fine-tuning context**. Actual teacher-output and full chat-template training lengths are also measured, including whether each fits 32k/48k. Targets are never truncated or used to guide selection; oversized examples remain tagged.

## Outputs and analysis

```text
report.md, summary.json          Coverage, compatibility, sizes, durations, errors
selected_ids.json               Frozen row IDs and selection information
manifest.json, runtime.json     Dataset/configuration/code/tools/tokenizer identity
master.jsonl                    All 200 selected originals and collection metadata
exports/baseline.jsonl           Fresh diagnostics, no internals
exports/20x3.jsonl               Same records/targets + small package
exports/50x3.jsonl               Same records/targets + large package
examples/safe-NNNNN/
  original.json, metadata.json, candidate.rs
  verification.json, source-context.json
  solver/                       Original queries, capture logs, original results
  internals/query-NNNN/         One replay's process, statistics and event sample
  collection.json              Concordance, capture/sampling limits and errors
  feedback-20x3.json, feedback-50x3.json
  messages-baseline.json, messages-20x3.json, messages-50x3.json
  target/                       Original reference, separate verification/preservation
  result.json                   Completed case; absent when pending
```

Exports contain exactly the same **completed** IDs and teacher outputs; failed validation or unavailable feedback does not remove a completed row. Missing cases remain in the master and summary. Exports are **unfiltered pilot views**, not a validated training dataset. Loss masking on assistant outputs must be implemented in the eventual trainer.

The report measures block and full-example token distributions (mean/median/P90/max), extra groups in 50x3, candidate-related groups omitted, replay concordance, source/target outcomes, collection phases and storage. Per-case times and artifact sizes should guide a later scale-up; do not extrapolate this stratified pilot as an unbiased distributional estimate.

## Resume

Run the same submission command with the same dataset, output and code. Completed records and saved successful stages are reused; missing/error examples are retried. Diagnostic replay timeouts/outcome mismatches are saved observations and are not automatically rerun until they happen to agree. Do not change code/tools/configuration while this job runs. Use another output for a new protocol.

To regenerate a report only, without tools, model or solver execution:

```bash
bash scripts/submit_safe_internals_report.sh
```

## References

- [Official SAFE training data](https://huggingface.co/datasets/microsoft/Verus_Training_Data): the SAFE file is separate from the other much larger files.
- [SAFE paper](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/ICLR_25_SelfEvolveAutoVerus.pdf).
