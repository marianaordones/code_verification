# Advanced Z3 evidence pilot

No LLM or Verus. Fresh diagnostic API replays; no claim of original search identity.
Planned context: 64k = base24k + previous-complement12k + new14k + output4k + other-input10k.
This pilot measures the NEW blocks only; whole future chat fit and L40S GPU capacity are not tested.

| Case | Mode | Matches | Qid unique / ambiguous / unmatched | Equality pairs / resolved | Binding paths resolved | Instance-term links | Chains | Non-inst clauses / specific hints | New tokens |
|---|---|---|---|---|---|---|---|---|---|
| sat_ground | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| sat_ground | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 1 / 0 | 111 |
| sat_ground | trace | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| sat_ground | combined | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 1 / 0 | 111 |
| sat_ground | combined_proof | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 3 / 0 | 259 |
| unsat_arithmetic | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| unsat_arithmetic | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| unsat_arithmetic | trace | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| unsat_arithmetic | combined | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| unsat_arithmetic | combined_proof | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 3 / 0 | 486 |
| unsat_quantified | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| unsat_quantified | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| unsat_quantified | trace | 1 | 0 / 0 / 1 | 0 / 0 | 1 | 0 | 0 | 0 / 0 | 554 |
| unsat_quantified | combined | 1 | 0 / 0 / 1 | 0 / 0 | 1 | 0 | 0 | 0 / 0 | 486 |
| unsat_quantified | combined_proof | 1 | 0 / 0 / 1 | 0 / 0 | 1 | 0 | 0 | 3 / 0 | 3201 |
| quantifier_without_ground_trigger | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| quantifier_without_ground_trigger | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| quantifier_without_ground_trigger | trace | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| quantifier_without_ground_trigger | combined | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| quantifier_without_ground_trigger | combined_proof | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 2 / 0 | 569 |
| matching_equality_chain | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 42 |
| matching_equality_chain | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 5 / 0 | 505 |
| matching_equality_chain | trace | 2 | 0 / 0 / 2 | 0 / 0 | 2 | 1 | 1 | 0 / 0 | 1311 |
| matching_equality_chain | combined | 2 | 0 / 0 / 2 | 0 / 0 | 2 | 1 | 1 | 5 / 0 | 2482 |
| matching_equality_chain | combined_proof | 2 | 0 / 0 / 2 | 0 / 0 | 1 | 1 | 1 | 12 / 0 | 6211 |

## Paired instrumentation measurements

| Case | Mode | Results | Median check s | Median process s | Check ratio | Changed outcomes | Changed reasons |
|---|---|---|---|---|---|---|---|
| sat_ground | baseline | {'sat': 1} | 0.03175779999583028 | 1.4105179000034695 | 1.0 | 0 | 0 |
| sat_ground | callback | {'sat': 1} | 0.00775689999863971 | 1.1791918999952031 | 0.24425180584480571 | 0 | 0 |
| sat_ground | trace | {'sat': 1} | 0.029308400000445545 | 1.455516300004092 | 0.9228724913027244 | 0 | 0 |
| sat_ground | combined | {'sat': 1} | 0.003521899998304434 | 1.3283412999880966 | 0.11089873979831255 | 0 | 0 |
| sat_ground | combined_proof | {'sat': 1} | 0.012001000010059215 | 1.6975557999976445 | 0.3778914160185817 | 0 | 0 |
| unsat_arithmetic | baseline | {'unsat': 1} | 0.03944740000588354 | 2.4912726000038674 | 1.0 | 0 | 0 |
| unsat_arithmetic | callback | {'unsat': 1} | 0.007991299993591383 | 2.112812400009716 | 0.20258115851487016 | 0 | 0 |
| unsat_arithmetic | trace | {'unsat': 1} | 0.031021499991766177 | 1.7096117999899434 | 0.7864016383117608 | 0 | 0 |
| unsat_arithmetic | combined | {'unsat': 1} | 0.004131599998800084 | 1.519156299997121 | 0.10473694079163291 | 0 | 0 |
| unsat_arithmetic | combined_proof | {'unsat': 1} | 0.012760700003127567 | 1.424385699996492 | 0.3234864655522119 | 0 | 0 |
| unsat_quantified | baseline | {'unsat': 1} | 0.0370173999981489 | 2.2938218000053894 | 1.0 | 0 | 0 |
| unsat_quantified | callback | {'unsat': 1} | 0.002891500000259839 | 1.1300912000006065 | 0.07811191494822521 | 0 | 0 |
| unsat_quantified | trace | {'unsat': 1} | 0.04756259999703616 | 1.318835099998978 | 1.2848714388210567 | 0 | 0 |
| unsat_quantified | combined | {'unsat': 1} | 0.003920799994375557 | 0.9802783000050113 | 0.10591775744843292 | 0 | 0 |
| unsat_quantified | combined_proof | {'unsat': 1} | 0.041229499998735264 | 2.236943700001575 | 1.1137870299047743 | 0 | 0 |
| quantifier_without_ground_trigger | baseline | {'unknown': 1} | 1.0368544000084512 | 2.422357600007672 | 1.0 | 0 | 0 |
| quantifier_without_ground_trigger | callback | {'unknown': 1} | 0.020067500008735806 | 2.25513740000315 | 0.019354212132940016 | 0 | 1 |
| quantifier_without_ground_trigger | trace | {'unknown': 1} | 1.0217234999872744 | 2.901759900007164 | 0.985406919215414 | 0 | 0 |
| quantifier_without_ground_trigger | combined | {'unknown': 1} | 0.009252600008039735 | 2.3101233999914257 | 0.008923721602535822 | 0 | 1 |
| quantifier_without_ground_trigger | combined_proof | {'unknown': 1} | 0.02013520000036806 | 2.230398800005787 | 0.01941950576686943 | 0 | 1 |
| matching_equality_chain | baseline | {'unsat': 1} | 0.05033800000092015 | 3.2324305000074673 | 1.0 | 0 | 0 |
| matching_equality_chain | callback | {'unsat': 1} | 0.010972999996738508 | 1.3652809999912279 | 0.21798641178707792 | 0 | 0 |
| matching_equality_chain | trace | {'unsat': 1} | 0.060739699998521246 | 1.5993673000048148 | 1.206637132929615 | 0 | 0 |
| matching_equality_chain | combined | {'unsat': 1} | 0.02058779999788385 | 1.537738700004411 | 0.40899121930763077 | 0 | 0 |
| matching_equality_chain | combined_proof | {'unsat': 1} | 0.046544700002414174 | 1.2061864999996033 | 0.9246434105757751 | 0 | 0 |

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
