# VerusBench loop_isolation(false):105 historical failures, two GPUs

Submit from the cluster repository root:

```bash
bash scripts/submit_verusbench_loop_isolation.sh
```

Optional arguments: completed original three-arm study, then NEW output directory. Defaults:
- source: results/verusbench-qwen14b-three-arms/seed-20261018
- output: results/verusbench-loop-isolation-false/seed-20261018

One CPU preparation freezes the same105 valid failed INITIAL candidates (not the last failed repair), verifies original hashes and candidate/response consistency, and transforms only loop-isolation attributes. A seeded shuffle20261018 creates disjoint50/55 task shards; IDs and exclusions are saved in selected_ids.json. The launcher submits TWO independent GPU jobs, each gres=gpu:1, QoS high,8CPU,64GB RAM,24h. They both depend only on preparation, NOT on each other; actual simultaneous start depends on resource availability. Slurm allocates distinct GPU resources; they may share a node. A CPU aggregation job runs after both finish/fail.

## Protocol

Only with_internals. Same Qwen2.5-Coder14B pinned revision, sampling,64k context,4096 output reserve, base24576 tokens, up to50 groups x3instances and3 concordant failing queries. No complement, advanced blocks or no-internals arm. Keep corrected v2 localized editor, rejection diagnostics and cast guidance. The only harness option is fixed loop_isolation(false), applied deterministically to executable/proof functions inside verus! macros; existing true settings are normalized to false. Spec functions without imperative loops are left unannotated unless an existing setting needs normalization. Other attributes, executable code, contracts and trusted/bypass prohibitions are unchanged. This is not a general permission for arbitrary model attributes. Lynette compares against the equally transformed original.

One saved initial generation + at mostTWO new localized repairs =THREE total model proposals. No new initial generation. Before any new model proposal, each shard checks the transformed candidates using native Verus/Lynette. Cases that verify from the option alone are reported as setting_only_success, NOT as model repairs. Every historical failure remains in the denominator105. Cases without safe sites/tool errors remain explicit; no false claim of proof impossibility.

Old SMT captures/replays are deliberately not copied: changing loop isolation changes the obligations. New Verus queries and fresh diagnostic replays are used for the option-specific candidate. This means model-feedback comparisons with old runs are exploratory; the proof context and solver observations change together. Attribute-only verification does not consume an LLM proposal. Initial checks run in each GPU allocation before loading Qwen; the model loads once per shard only if some cases still need repair.

## Outputs/resume

- manifest.json,selected_ids.json: source, settings, hashes, all105 IDs and disjoint batches.
- frozen/inputs/: unmodified and transformed source/candidate, transformation edit log, original diagnostics.
- batch50/,batch55/: independent runtime locks, new initial Verus checks, model repairs, reports and error records.
- comparison.md/json: aggregate option-only successes, successes through1/2 repairs, model-only repairs, token/context checks and missing IDs. Do not count option-only successes as evidence that internals helped.

Resume with the same launcher and unchanged code. Completed per-task results and responses are reused. To rerun only a failed GPU shard:

```bash
sbatch scripts/slurm/verusbench_loop_run.slurm results/verusbench-loop-isolation-false/seed-20261018 batch50
```

Use batch55 for the other. Refresh aggregation with:

```bash
sbatch scripts/slurm/verusbench_loop_compare.slurm results/verusbench-loop-isolation-false/seed-20261018
```

Update baseline/,prompts/,scripts/,tests/; existing repair_study/,solver_needs_study/,diagnostics/ must remain compatible. Do NOT update the checkout between preparation and completion. Native tools can still be found through VERUSBENCH_TOOLS_DIR or the old sibling cache. No changes to old result directories; no live cluster submission or real model/Verus execution during implementation.
