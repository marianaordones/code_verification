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
| unsat_quantified | trace | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| unsat_quantified | combined | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| quantifier_without_ground_trigger | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| quantifier_without_ground_trigger | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| quantifier_without_ground_trigger | trace | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| quantifier_without_ground_trigger | combined | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| matching_equality_chain | baseline | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| matching_equality_chain | callback | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 4 / 0 | 424 |
| matching_equality_chain | trace | 0 | 0 / 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 | 48 |
| matching_equality_chain | combined | 2 | 2 / 0 / 0 | 0 / 0 | 2 | 1 | 1 | 4 / 0 | 1424 |

## Available blocks and selected 14k package (first repetition)

| Case | Mode | Matching available / sent | Chains available / sent | Clauses available / sent | Tokens available: matching / chains / clauses | Selected tokens |
|---|---|---|---|---|---|---|
| sat_ground | combined | 0 / 0 | 0 / 0 | 1 / 1 | None / None / None | 117 |
| unsat_arithmetic | combined | 0 / 0 | 0 / 0 | 0 / 0 | None / None / None | 48 |
| unsat_quantified | combined | 0 / 0 | 0 / 0 | 0 / 0 | None / None / None | 48 |
| quantifier_without_ground_trigger | combined | 0 / 0 | 0 / 0 | 0 / 0 | None / None / None | 48 |
| matching_equality_chain | combined | 2 / 2 | 1 / 1 | 4 / 4 | None / None / None | 1424 |

## Paired instrumentation measurements

| Case | Mode | Results | Median check s | Median process s | Check ratio | Changed outcomes | Changed reasons |
|---|---|---|---|---|---|---|---|
| sat_ground | baseline | {'sat': 1} | 0.03453790000639856 | 1.7856251999910455 | 1.0 | 0 | 0 |
| sat_ground | callback | {'sat': 1} | 0.006106600005296059 | 1.3798376000049757 | 0.17680866538396192 | 0 | 0 |
| sat_ground | trace | {'sat': 1} | 0.03785020000941586 | 1.7265023999934783 | 1.0959033410370536 | 0 | 0 |
| sat_ground | combined | {'sat': 1} | 0.007298999989870936 | 1.6859196000004886 | 0.21133305697563282 | 0 | 0 |
| unsat_arithmetic | baseline | {'unsat': 1} | 0.02681420001317747 | 1.6941825999965658 | 1.0 | 0 | 0 |
| unsat_arithmetic | callback | {'unsat': 1} | 0.003656899993075058 | 1.3388745999982348 | 0.1363792315742377 | 0 | 0 |
| unsat_arithmetic | trace | {'unsat': 1} | 0.048051200006739236 | 1.6458741999958875 | 1.7920057276788095 | 0 | 0 |
| unsat_arithmetic | combined | {'unsat': 1} | 0.003159800005960278 | 1.51960980000149 | 0.11784054733713623 | 0 | 0 |
| unsat_quantified | baseline | {'unsat': 1} | 0.04757330000575166 | 1.715120000008028 | 1.0 | 0 | 0 |
| unsat_quantified | callback | {'unsat': 1} | 0.009136799999396317 | 3.3031006999954116 | 0.19205730942128607 | 0 | 0 |
| unsat_quantified | trace | {'unsat': 1} | 0.028560899998410605 | 1.574386799999047 | 0.600355661578187 | 0 | 0 |
| unsat_quantified | combined | {'unsat': 1} | 0.0038467999984277412 | 1.7596474000019953 | 0.08086048262287163 | 0 | 0 |
| quantifier_without_ground_trigger | baseline | {'unknown': 1} | 1.067633400001796 | 3.663628799986327 | 1.0 | 0 | 0 |
| quantifier_without_ground_trigger | callback | {'unknown': 1} | 0.0047122999967541546 | 2.01659679999284 | 0.004413780982073273 | 0 | 1 |
| quantifier_without_ground_trigger | trace | {'unknown': 1} | 1.051320400001714 | 2.640124099998502 | 0.9847204105828326 | 0 | 0 |
| quantifier_without_ground_trigger | combined | {'unknown': 1} | 0.004279300002963282 | 1.9713287000049604 | 0.00400821106098412 | 0 | 1 |
| matching_equality_chain | baseline | {'unsat': 1} | 0.04183940000075381 | 1.5519435000023805 | 1.0 | 0 | 0 |
| matching_equality_chain | callback | {'unsat': 1} | 0.0152451000030851 | 1.4456448999990243 | 0.36437186008428496 | 0 | 0 |
| matching_equality_chain | trace | {'unsat': 1} | 0.05357220000587404 | 1.5871956000046339 | 1.2804246715992302 | 0 | 0 |
| matching_equality_chain | combined | {'unsat': 1} | 0.00848730000143405 | 1.4717476000078022 | 0.20285424746246686 | 0 | 0 |

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
- Complete processes: False
