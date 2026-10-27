# Full VerusBench, three feedback conditions

Run from the cluster repository root:

```bash
bash scripts/submit_verusbench_three_arms.sh
```

Uses existing VerusBench data/manifest.json and the previously prepared native tool bundle (.cluster/tools-native.*); no Solver Needs dataset required. QoS high, one GPU,64GB host RAM,24hours. Model loaded once for all arms. BF16 Qwen2.5-Coder14B, pinned revision,64k YaRN2 and GPU memory utilization0.95. Uses the original VerusBench-compatible Verus33269ac and Lynette, not the newer Solver Needs Verus.

All150 official tasks, same seed20261018 and three TOTAL proposals (initial plus two repairs). First proposal generated AND verified once per task in shared/; all three arms receive byte-identical request/response/program/verification/integrity/result copies. Initial success counts equally for all. No initial solver feedback is supplied. On repair:

* no_internals: conventional Verus diagnostics and integrity diagnostics only.
* base24k: same diagnostics plus up to24576 tokens,50 quantifier groups,3 instances/group, up to3 outcome-concordant SAT/UNKNOWN diagnostic replays.
* base24k_complement12k: same base plus up to12288 tokens of the previous complement, including up to20 relevant unique-qid formulas without observed callback events, input term examples and observed counts for base groups.

First repair base package is constructed once and shared exactly between the two internal arms, using the full-package selection. Later candidates diverge and receive their own feedback. All arms receive the same v4 full-file-generation prompt with the existing internals/complement interpretation guides. This keeps instructions identical while varying data. No Solver Needs law catalogue, restricted JSON actions or localized slots are introduced. Implementation/contracts stay protected by the original integrity checker; success requires whole-program Verus verification AND integrity.

Context65536, output reserve4096. Exact full-chat measurements include current/original program, diagnostics and guides. Whole feedback items are omitted if needed; no silent program truncation, context reduction or offload. No SMT query is sent. Replays are separate searches, not attributed to original Verus execution.

comparison.md/json report success through1/2/3, categories, pairwise exclusive IDs, first-proposal equality, missing cases and context checks. Per-arm token totals include the shared initial proposal for a fair logical comparison; do not sum them as actual GPU usage. Shared generation physically occurs once. Resume by submitting the same command with unchanged code/config. Do not update the checkout while a job is active.

Update baseline/, solver_needs_study/, repair_study/, diagnostics/, prompts/, configs/, scripts/, tests/.
