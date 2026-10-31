# SAFE / VerusBench overlap screening

24,828 SAFE rows; 150 VerusBench tasks. Both first input program and target were screened.

Token-exact matches: 0. Near-match flags: 52, covering 34 SAFE rows. Parse errors: 0.

Near-match criterion: at least 80% of benchmark 12-token shingles present in a SAFE program. These are review flags, not 34 proven identical problems. Renamed or substantially edited variants may be missed.

Manual inspection confirmed related variants for safe-04331 / misc_tail_triangle, safe-07278 / diffy_brs3, and safe-09119 / misc_map. Contracts, bounds and proof annotations differ.

Preparation excludes flagged connected families conservatively; overlap.json lists all flags.

| SAFE row | VerusBench task | Field | Coverage |
|---|---|---|---|
| safe-01295 | diffy_res1o | input | 80.5% |
| safe-04331 | misc_tail_triangle | input | 86.1% |
| safe-04338 | diffy_brs4 | input | 88.9% |
| safe-04338 | diffy_brs5 | input | 81.1% |
| safe-04345 | diffy_res1o | input | 82.4% |
| safe-04994 | diffy_res1o | input | 80.5% |
| safe-05029 | diffy_res1o | input | 80.5% |
| safe-05431 | diffy_res1o | input | 81.0% |
| safe-05650 | diffy_ms3 | input | 81.2% |
| safe-05650 | diffy_ms4 | input | 93.2% |
| safe-05650 | diffy_ms5 | input | 81.2% |
| safe-05650 | diffy_ms4 | output | 81.2% |
| safe-07278 | diffy_brs3 | input | 93.7% |
| safe-07278 | diffy_brs3 | output | 84.2% |
| safe-07344 | diffy_res1o | input | 81.0% |
| safe-07719 | diffy_ms3 | input | 81.2% |
| safe-07719 | diffy_ms4 | input | 81.2% |
| safe-07719 | diffy_ms5 | input | 81.2% |
| safe-07842 | diffy_s2lif | input | 80.7% |
| safe-09119 | misc_map | input | 92.7% |
| safe-09119 | misc_map | output | 86.1% |
| safe-10480 | diffy_res1o | input | 80.5% |
| safe-11844 | diffy_ms3 | input | 93.2% |
| safe-11844 | diffy_ms4 | input | 81.2% |
| safe-11844 | diffy_ms5 | input | 81.2% |
| safe-12299 | misc_findmax | input | 80.1% |
| safe-14001 | diffy_ms3 | input | 88.1% |
| safe-14001 | diffy_ms4 | input | 86.4% |
| safe-14001 | diffy_ms5 | input | 81.2% |
| safe-14887 | diffy_res1o | input | 82.4% |
| safe-17649 | diffy_res1o | input | 80.5% |
| safe-19488 | diffy_ms3 | input | 81.2% |
| safe-19488 | diffy_ms4 | input | 81.2% |
| safe-19488 | diffy_ms5 | input | 81.2% |
| safe-19631 | diffy_res1o | input | 81.5% |
| safe-20349 | diffy_brs2 | input | 80.5% |
| safe-20425 | diffy_res1o | input | 82.4% |
| safe-21364 | diffy_res1o | input | 80.5% |
| safe-21416 | diffy_ms5 | input | 81.8% |
| safe-21755 | diffy_ms3 | input | 80.1% |
| safe-21755 | diffy_ms4 | input | 80.1% |
| safe-21755 | diffy_ms5 | input | 85.2% |
| safe-22244 | diffy_ms3 | input | 81.2% |
| safe-22244 | diffy_ms4 | input | 88.1% |
| safe-22244 | diffy_ms5 | input | 86.4% |
| safe-22262 | diffy_ms5 | input | 81.8% |
| safe-22437 | diffy_res1o | input | 82.4% |
| safe-22592 | diffy_res1o | input | 82.4% |
| safe-22817 | diffy_res1o | input | 80.5% |
| safe-22864 | diffy_res1o | input | 80.5% |
| safe-23278 | diffy_res1o | input | 82.4% |
| safe-24813 | diffy_sina1 | input | 85.1% |
