# Missing assertions: Opus 4.8 Low, shared first action, 50x3 cap

The exact 100 IDs supplied by the user are fixed in
`configs/missing-opus48-user100.json`; they match the original fixed 100-ID list.
Pilot selection is the FIRST 20 in that order, with no outcome-based selection:
4 AX, 4 INST-forall, and 3 each INST-witness, NLA, FUEL, Other. These IDs are
exploratory and include tasks already used in earlier studies; do not call them
an unseen confirmatory sample. The other 80 IDs are recorded but not executed.

Model `claude-opus-4-8`, explicit Low. Official Claude Code uses the native Pro
login, no tools/customizations/automatic retries. Model ID is audited in the raw
transcript; unavailable/changed model stops execution instead of silently choosing
Opus 5.5. Subscription availability must be checked for the account. No API
purchase or extra paid usage is enabled. Keep account extra paid usage disabled.

## Protocol

Reuse the solver-needs pinned dataset, assertion-removal applicator and published
validation policy. Verus 0.2026.02.22.2c9a6a0, bundled Z3 4.12.5, Rust 1.93.0.
Do NOT use the older VerusBench bundle or its full-file output protocol.
The removed assertion/reference is never sent. The model returns the existing
four-field JSON (`mechanism`, `statements`, optional checked `law`, Boolean `nla`).
One action replaces the proof region and previous settings. Verified catalogue
laws and the explicit smt.arith.nl option remain equally available to both arms.

Generate proposal 1 ONCE without internals. If it succeeds, stop that case and
report it as common initial success. Otherwise freeze the candidate, action/NLA
settings, diagnostics, initial history, response and selected feedback. Proposals
2 and 3 run in both arms, starting at EXACTLY this failed state. Only treatment
gets the internals block; common prompt/candidate/checkpoint hashes audit proposal
2 equality. At proposal 3 each branch follows its own candidate and diagnostics.
Invalid JSON, disallowed/empty/repeated actions consume a proposal, preserving
the previous candidate/settings. Whole-file Verus verification decides success.
No Lynette is needed because source outside the validated proof slot is preserved
mechanically. An initially verifying removed-assertion candidate is separate.

One captured SAT/UNKNOWN query is replayed, five diagnostic seconds; only
outcome-concordant results are exposed. Up to 50 quantifier groups, 3 instances
each, ranked by the existing source/operation heuristics. Background quotas remain.
The worker keeps its existing reservoir of up to 128 groups. The 12,288-token
internals budget and 49,152-token prompt envelope are measured with the pinned
Qwen tokenizer, NOT Claude's tokenizer. Groups/instances may be below caps. Each
request records actual query/group/instance/token counts in `exposure.json`.
No SMT full query, model, unsat core, proof or unobserved-quantifier complement
is added. The output reserve of 4,096 Qwen tokens does not cap Claude's output.
Seed and temperature are uncontrolled and recorded null.

## WSL

After synchronizing the new runner, scoped prompt, configs and compatible feedback
module into WSL (no old source is overwritten without a snapshot):

```bash
cd ~/projects/code_verification
bash scripts/run_missing_opus48_shared20.sh prepare
bash scripts/run_missing_opus48_shared20.sh run
cat results/missing-opus48-low-shared20-50x3-v1/comparison.md
```

Preparation never calls Claude. It checks only removed-assertion candidates,
captures initial diagnostics and records already-verifying cases. The model's
initial feedback is always WITHOUT internals. Diagnostic packets are built only
for the failed shared proposal, then updated for the treated third proposal.
Maximum 100 requests: twenty shared proposals plus 2 arms x 2 repairs x 20 failures.
Most cases may succeed immediately; the repair denominator is the number of
FAILED shared proposals, not automatically 20. The report separates these counts
and the repairs at proposals 2 and 3, plus actual exposed attempts.

Keep the runtime/CLI/config/code unchanged for resumption. Saved completed
responses are reused. Quota/transport/timeouts stop, never automatically resubmit
an ambiguous pending call. The old studies/results remain separate.
