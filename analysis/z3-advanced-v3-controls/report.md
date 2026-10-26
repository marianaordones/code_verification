# Advanced Z3 evidence pilot

No LLM or Verus. Fresh diagnostic API replays; no claim of original search identity.
Planned context: 64k = base24k + previous-complement12k + new14k + output4k + other-input10k.
This pilot measures the NEW blocks only; whole future chat fit and L40S GPU capacity are not tested.

| Case | Mode | Matches | Qid unique / ambiguous / unmatched | Equality pairs / resolved | Binding paths resolved | Instance-term links | Chains | Non-inst clauses / specific hints | New tokens |
|---|---|---|---|---|---|---|---|---|---|
| sat_ground | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| sat_ground | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 1 / 0 | 117 |
| sat_ground | trace | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| sat_ground | combined | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 1 / 0 | 117 |
| unsat_arithmetic | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| unsat_arithmetic | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| unsat_arithmetic | trace | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| unsat_arithmetic | combined | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| unsat_quantified | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| unsat_quantified | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| unsat_quantified | trace | 1 | 1 / 0 / 0 | 0 / 0 | 1 | 0 | 0 | 0 / 0 | 462 |
| unsat_quantified | combined | 1 | 1 / 0 / 0 | 0 / 0 | 1 | 0 | 0 | 0 / 0 | 462 |
| quantifier_without_ground_trigger | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| quantifier_without_ground_trigger | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| quantifier_without_ground_trigger | trace | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| quantifier_without_ground_trigger | combined | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| matching_equality_chain | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| matching_equality_chain | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 4 / 0 | 424 |
| matching_equality_chain | trace | 2 | 2 / 0 / 0 | 0 / 0 | 2 | 1 | 1 | 0 / 0 | 1010 |
| matching_equality_chain | combined | 2 | 2 / 0 / 0 | 0 / 0 | 2 | 1 | 1 | 4 / 0 | 1424 |

## Available blocks and selected 14k package (first repetition)

| Case | Mode | Matching available / sent | Chains available / sent | Clauses available / sent | Tokens available: matching / chains / clauses | Selected tokens |
|---|---|---|---|---|---|---|
| sat_ground | combined | 0 / 0 | 0 / 0 | 1 / 1 | None / None / None | 117 |
| unsat_arithmetic | combined | 0 / 0 | 0 / 0 | 0 / 0 | None / None / None | 48 |
| unsat_quantified | combined | 1 / 1 | 0 / 0 | 0 / 0 | None / None / None | 462 |
| quantifier_without_ground_trigger | combined | 0 / 0 | 0 / 0 | 0 / 0 | None / None / None | 48 |
| matching_equality_chain | combined | 2 / 2 | 1 / 1 | 4 / 4 | None / None / None | 1424 |

## Paired instrumentation measurements

| Case | Mode | Results | Median check s | Median process s | Check ratio | Changed outcomes | Changed reasons |
|---|---|---|---|---|---|---|---|
| sat_ground | baseline | {'sat': 1} | 0.03374990000156686 | 1.9785480999998981 | 1.0 | 0 | 0 |
| sat_ground | callback | {'sat': 1} | 0.0035865999961970374 | 1.4659784000104992 | 0.10626994438592492 | 0 | 0 |
| sat_ground | trace | {'sat': 1} | 0.03625439999450464 | 1.5048887000011746 | 1.0742076270691618 | 0 | 0 |
| sat_ground | combined | {'sat': 1} | 0.00670269998954609 | 1.26824880001368 | 0.19859910664135047 | 0 | 0 |
| unsat_arithmetic | baseline | {'unsat': 1} | 0.03543800000625197 | 1.427396700004465 | 1.0 | 0 | 0 |
| unsat_arithmetic | callback | {'unsat': 1} | 0.0034832000092137605 | 1.5339022999978624 | 0.09828997145999364 | 0 | 0 |
| unsat_arithmetic | trace | {'unsat': 1} | 0.020851799999945797 | 1.4226669000054244 | 0.5884022799330415 | 0 | 0 |
| unsat_arithmetic | combined | {'unsat': 1} | 0.0062360000010812655 | 1.3669117000099504 | 0.17596929849260995 | 0 | 0 |
| unsat_quantified | baseline | {'unsat': 1} | 0.022728099997038953 | 1.318318999998155 | 1.0 | 0 | 0 |
| unsat_quantified | callback | {'unsat': 1} | 0.003579399999580346 | 1.2715711000055308 | 0.15748786744367876 | 0 | 0 |
| unsat_quantified | trace | {'unsat': 1} | 0.03279810000094585 | 1.3110715999937383 | 1.443063872704662 | 0 | 0 |
| unsat_quantified | combined | {'unsat': 1} | 0.002708100000745617 | 1.3081046000006609 | 0.11915206291324096 | 0 | 0 |
| quantifier_without_ground_trigger | baseline | {'unknown': 1} | 1.0245018000132404 | 2.346717599997646 | 1.0 | 0 | 0 |
| quantifier_without_ground_trigger | callback | {'unknown': 1} | 0.004443500001798384 | 1.2739569999976084 | 0.004337230058298538 | 0 | 1 |
| quantifier_without_ground_trigger | trace | {'unknown': 1} | 1.0320594999939203 | 2.2476435999997193 | 1.0073769513929427 | 0 | 0 |
| quantifier_without_ground_trigger | combined | {'unknown': 1} | 0.00820430000021588 | 1.6408653999969829 | 0.008008087443194195 | 0 | 1 |
| matching_equality_chain | baseline | {'unsat': 1} | 0.04293820000020787 | 1.434490100000403 | 1.0 | 0 | 0 |
| matching_equality_chain | callback | {'unsat': 1} | 0.012911199999507517 | 1.440531899992493 | 0.3006926233387755 | 0 | 0 |
| matching_equality_chain | trace | {'unsat': 1} | 0.06314619998738635 | 1.5286195000080625 | 1.4706298817155972 | 0 | 0 |
| matching_equality_chain | combined | {'unsat': 1} | 0.033111700002336875 | 1.9472318000043742 | 0.7711478357773864 | 0 | 0 |

## Interpretation

- combined_proof explicitly enables proof mode: report its semantic/performance effect separately.
- Unique qid association does not prove equality between an input formula and its transformed search version.
- Missing equality roots, ambiguous qids, unmatched IDs, truncation and callback errors remain explicit.
- Chains use earlier instance-associated enodes later named in a match. They do not prove first creation, necessity, or complete causality.
- Clause dependencies are raw callback values, not resolved to trace event IDs; branch validity is not reconstructed.
- Raw trace terms may be partial renderings; retain IDs and raw records. Do not feed unresolved explanations as complete proofs.
- Per-block tokens and capped package costs are in report.json; no approximate word-to-token conversion.
- Timing ratios for tiny checks or timeouts are unstable. Same result does not imply same search.
- Missing real categories: []
- Tokenizer: .cluster\audit-python\qwen-coder-tokenizer.json
- Complete processes: True
