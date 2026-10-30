# SAFE 1000: proof-attribute policy v2 and validated export

This runs 1,000 repair examples, including the original 200 as the exact prefix, with every example executed again in a new directory. No old inference/solver artifacts are imported. IDs and input hashes are frozen in `configs/safe-repair-pilot1000.json`. The original 200 results remain untouched.

## Submit on the cluster

Finish jobs using this checkout before updating it. Update `safe_internals/`, `configs/`, `scripts/`, `tests/` and `docs/` (or the repository). The existing dataset, CPU package cache, Rust installation and native tools bundle are reused.

From the repository root:

```bash
bash scripts/submit_safe_internals_1000.sh
```

Default input: `data/safe/sft_safe_25k.json`. An existing path and an output override are supported:

```bash
bash scripts/submit_safe_internals_1000.sh "/path/sft_safe_25k.json"
```

Default output: `results/safe-internals-pilot1000-attrs-v2/seed-20261018/`. Same CPU resources: four CPUs, 32G RAM, 24 hours, high QoS, two concurrent examples, no GPU/model inference. Both 12,288/20x3 and 24,576/50x3 packets are constructed from the same bounded saved events, with the same capture/replay limits as the 200-example pilot.

The first 200 are guaranteed to match the original frozen IDs and order, followed by 800 additional distinct input programs chosen by the same deterministic diagnostic/isolation stratification. Targets do not guide selection. These 1,000 are examples to audit, not 1,000 already-valid training pairs. Selection is diverse, not a representative random estimate of dataset prevalence.

## Exactly what changes in preservation

The new policy applies only to the SAFE collector. The global VerusBench/Solver Needs integrity rules are unchanged.

For AST comparison only, two copies are created from the input and target. Both copies omit these exact attributes:

- `#[verifier::loop_isolation(false)]`
- Supported proof-trigger attributes already recognized by the guard: `#[trigger]`, `#[trigger(N)]` for a numeric group, and `#![auto]`.

This allows addition/removal or relocation of those annotations. The actual input and actual target are still verified unchanged; their attributes are not removed for execution or internals collection. The comparison metadata records every ignored attribute and offset under policy `safe-proof-attributes-v2`.

All other attributes remain protected. In particular, this does not grant an exemption to `loop_isolation(true)`, external_body, arbitrary verifier attributes, assume, unsafe, contract changes or executable changes. The usual lexical trust guard and Lynette AST comparison run on the normalized copies. Added empty `loop {}` constructs are explicitly rejected even before AST comparison. Other executable loop/return/body changes still require the unchanged strict AST gate; they are not silently approved.

Parser/checker errors remain pending/unaccepted, not confirmed executable violations. This patch does not fix the known cast/parser or empty-statement issues in Lynette, so some legitimate examples may still require later review. No broad parser fallback automatically approves them.

The SAFE-only diagnostic classifier also treats explicit `error[E...]` compiler diagnostics as compilation errors even if they contain “not satisfied”, preventing the observed trait-error misclassification. The global classifier and historical records are unchanged.

## Filtering for eventual fine-tuning

All 1,000 originals, artifacts and validation decisions remain in `master.jsonl`. Completed examples are retained in the unfiltered views:

```text
exports/baseline.jsonl
exports/20x3.jsonl
exports/50x3.jsonl
```

A separate candidate-positive export is produced:

```text
exports/validated/baseline.jsonl
exports/validated/20x3.jsonl
exports/validated/50x3.jsonl
```

A row enters that export only if:

1. Its target was accepted by Verus.
2. Preservation passed under the stated policy.
3. No actual target assume call was found, and lexical tagging completed.
4. The input did not already verify without repair.

The three validated views contain identical IDs and targets. Internals are not required for inclusion: a verified syntax/type repair may legitimately have no SMT events; its views are identical if no packet is available. `summary.json` separately reports `training_eligible` and `training_eligible_with_internals`. `training-eligibility.json` records exclusion reasons, which may overlap. Failed/pending/unsafe records remain in the master and unfiltered export but not in validated positives.

“Validated” means these gates passed, not that data is already split or free of benchmark contamination. Before training, choose family-based splits, check benchmark overlap and lengths, and implement assistant-only loss. No target is truncated or silently fixed. No training is executed by these scripts.

## Resume/report

Resubmit the same command with the same code, tools and output to resume. To report without solver calls:

```bash
bash scripts/submit_safe_internals_report.sh \
  results/safe-internals-pilot1000-attrs-v2/seed-20261018
```

Read `report.md`, `summary.json` and `training-eligibility.json` for raw coverage, approval counts and exclusion causes. Do not point this new protocol at the completed 200-example output; implementation/policy fingerprints intentionally reject that reuse.
