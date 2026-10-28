# VerusBench localized repair v2: four total proposals

From the updated cluster repository root:

```bash
bash scripts/submit_verusbench_local_v2.sh
```

Optional arguments: completed ORIGINAL three-arm source directory, then a NEW output directory. Defaults:
- source: results/verusbench-qwen14b-three-arms/seed-20261018
- output: results/verusbench-local-v2-base24k-four/seed-20261018

This is a separate module/editor/launcher; previous experiment directories are not migrated. Do not update the checkout during preparation/execution. CPU preparation freezes the same150 shared initial generations. Initial successes and integrity/editor exclusions remain explicit; the two arms repair the same eligible failed candidates.

without_internals receives conventional Verus/integrity diagnostics only. with_internals adds the same up-to24k50groups x3instances package; no complement/advanced blocks/full SMT query. Three NEW localized proposals per arm after the saved initial generation = FOUR TOTAL proposals. The initial generation is not rerun. Cast guidance therefore applies from the FIRST REPAIR, identically in both arms. Context64k, output reserve4096, same pinned Qwen/sampling and VerusBench tools. Source cached initial events reused/repackaged when present. No local/cluster inference was performed during implementation.

## Body-only sites

The new regions_v2 editor recognizes executable/proof function bodies; it excludes function contracts and spec-function bodies. Insertions are offered at conservative statement boundaries, including final expressions like arr[i], max or None, and within recognized if/else/loop blocks. It does not descend into closure bodies, struct literals, match-arm patterns or arbitrary braced expressions. Match-arm internals and ambiguous inline contracts are deliberately unsupported. Existing loop invariant lists and proof blocks can be replaced; only one region per response. Verus and Lynette still decide acceptance, so the lexical scanner is not a replacement Verus parser.

## Rejected response feedback

The prompt includes a separate rejected_edit block containing previous response, classification, edit error, integrity reason and actual Verus stdout/stderr. It explicitly states that this edit was NOT applied. current_candidate/verus_diagnostics remain attached to the retained program. Rejected response data is included in exact full-chat budgeting. The retained solver capture is propagated across consecutive rejections, avoiding replay of the rejected program as if it were current state.

## Metrics

- edit_error: invalid JSON/site, unchanged replacement, unsupported local-edit shape.
- unparseable: proposed source failed parsing (Lynette unparseable or Verus syntax). It is NOT a forbidden change.
- forbidden_change: an actual invalid preservation-policy result. Reasons are retained for inspection.
- proof_or_compilation_failure: structurally accepted edit still failed typechecking or proof.
- verified: complete Verus AND preservation success.
- checker/verifier infrastructure errors stay pending, not falsely counted as forbidden modifications.

All rejections consume a proposal and retain the previous candidate. Initial exclusions are split into initial_unparseable, initial_forbidden_change and initial_integrity_error. Comparison records repaired_by_repair1/2/3, known_successes_by_overall_proposal1/2/3/4, statuses, context checks and paired first-repair equality. Changing multiple aspects simultaneously means this is a new repair-policy experiment, not an isolated causal estimate of each correction.

## Prompt addition (excerpt)

Do NOT write `0 <= i as int < N as int`. Write `0 <= (i as int) && (i as int) < (N as int)`. Use `forall|j: int| 0 <= j < (i as int) ==> P(j)` where appropriate. Seq/Vec-view proof indices use int according to expression type; do not rewrite executable indexing. Parsing correctness does not establish invariant truth.

Full text: prompts/verusbench-local-v2.txt. Identical instructions and rejection feedback policy in both arms.

Update baseline/, repair_study/, prompts/, scripts/, tests/ (and keep existing solver_needs_study/,diagnostics/ compatible). The native tools can be reused via VERUSBENCH_TOOLS_DIR or the old sibling cache. Submission is QoS high, CPU preparation then one GPU for both arms,64GB host RAM,24h. Scripts use the same cluster runtime/IPC safeguards as prior experiments.
