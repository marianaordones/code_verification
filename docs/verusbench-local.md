# VerusBench localized repair: base24k ablation

Submit from the cluster repository root, after updating the code:

```bash
bash scripts/submit_verusbench_local.sh
```

Optional arguments are source completed three-arm run, then a NEW output directory. Defaults:
- source: results/verusbench-qwen14b-three-arms/seed-20261018
- output: results/verusbench-local-base24k/seed-20261018

CPU preparation freezes the same saved shared initial candidates and original programs. No new initial LLM generation, Verus run or source screening is performed. It verifies original hashes, response-to-candidate correspondence and saved success consistency; source execution authenticity is inherited, not independently certified. All150 tasks remain visible in manifest/selection. Existing successful candidates, integrity-rejected candidates and editor-unavailable cases are explicit exclusions from the REPAIR denominator. They are not silently treated as unprovable. Two new proposals per arm plus the saved first proposal = three TOTAL proposals. Both arms start from identical eligible failed candidates and seeds20261019/20261020.

One GPU runs without_internals vs with_internals. Both use identical localized JSON instructions and ordinary Verus/integrity diagnostics/source context. Only with_internals receives up to24576 tokens of relevance-ranked50groups x3instances across up to3 outcome-concordant SAT/UNKNOWN replays. No complementary12k, advanced blocks or SMT query. Initial raw events are reused from shared initial-feedback when available, REPACKAGED for the real localized prompt. Missing saved events are collected anew and recorded. Subsequent failures use the current retained candidate. Context65536, output reserve4096, same Qwen model/revision/sampling and VerusBench-compatible tools. Both guides are identical; internals absent in control.

The existing conservative region editor offers invariant-list replacement, existing proof-block replacement and proof-block insertion before recognized statements. Exactly one region per response. New standalone lemma definitions/arbitrary executable locations are not supported. Region counts/kinds, parser failures, offered locations, selected IDs, no-change/invalid edits and integrity failures are saved. No-site cases are editor limitations, not demonstrations of proof impossibility. Accepted edits are always verified with Verus and Lynette. Rejected edits consume a proposal but the next state retains the previous preserved program.

comparison.md/json include repair success through1/2, categories, exclusive successes, shared first-repair prompt checks, context checks, costs, explicit exclusions and remaining cases. known_full_benchmark_successes includes saved initial successes; repair rates must use the stated eligible denominator. Runtime errors remain pending. Resubmit the same launcher with unchanged code/config to resume. Do not update checkout between preparation and completion.

Update baseline/, solver_needs_study/, repair_study/, diagnostics/, prompts/, scripts/, tests/. Existing cluster runtime/tool bundles are required. QoS high, one GPU,64GB host RAM,24hours.
