# Localized evaluation of the trained SAFE adapter

Two separate studies, each with without_internals and with_internals arms:
150 VerusBench tasks and all 462 Solver Needs Verus/Z3 tasks. The adapter, base
model, temperatures, context and native tools are the same as the current full-file
evaluation. No further training and no changes to the existing sft_eval runner.

## Submit

The source evaluations must already have their manifests under
results/safe-sft-eval-v1/{verusbench,solver-needs}. VerusBench must have all shared
proposal_01 records. Solver Needs needs only completed preparation, not a finished
GPU run. The new scripts read the source without modifying it; both old/new
evaluations may run concurrently if enough GPUs are available.

```bash
SFT_GPU_TYPE=L40S bash scripts/submit_safe_sft_local.sh all
```

This submits CPU preparation -> GPU run -> report for each dataset. One GPU per
dataset; both arms are handled by the same model load. Use SFT_GPU_TYPE=A100 to
request that Slurm type. high_performance / high for GPU, new_p_general / high for
CPU, with the existing held-job exclusion workaround. Default GPU limit 48h.

One dataset only, with explicit source and output parents:

```bash
SFT_GPU_TYPE=A100 bash scripts/submit_safe_sft_local.sh solver-needs \
  results/safe-sft-eval-v1 results/safe-sft-local-v1
```

Reports: results/safe-sft-local-v1/{verusbench,solver-needs}/comparison.md and
comparison.json. Detailed requests, JSON responses, edit errors, preservation,
Verus diagnostics and solver packets are retained. Submission IDs are printed and
stored in logs/safe-local-submission-*.tsv.

## Proposals and editable actions

VerusBench reuses the fine-tuned model's actual shared first full-file proposal
from the existing evaluation. Initially verified proposals remain known successes
without further generation. Each eligible failed candidate gets TWO localized
repairs, hence THREE total proposals including the saved first. Results therefore
can be compared on the same initial failures and matched repair seeds. The v2
body-only editor offers invariant-list replacements, proof-block replacements,
and proof insertions at safe statement/final-expression boundaries. Contracts are
excluded. Exactly one offered site_id/replacement JSON object is accepted. The
SAFE preservation policy checks the resulting program against the original task.
Initial rejected candidates, no-safe-site/parser errors and editor restrictions
are separately counted, not described as proof impossibility. Existing passing
initial proposals are not counted as successful new repairs.

Solver Needs uses the SAME stripped initial programs as the full-file evaluation.
It restores the old localized JSON interface: mechanism/statements/law/nla.
Statements replace the contents of the marked missing-proof slot, with one optional
checked catalogue law and the explicit nonlinear-arithmetic solver toggle. Three
TOTAL actions are permitted. Actual labels, removed assertions and successful
probes are hidden. The catalogue is identical across tasks/arms; imported laws
are checked by whole-file Verus verification, not accepted as trusted axioms.
This changes the available settings/law actions as well as output length relative
to the full-file run; attribute any difference to this interface as a whole.

Invalid JSON, empty/no-op edits and refused edits consume a proposal. They leave
the current candidate intact and appear in a separate rejection block next time.
Accepted edits that still fail verification become the next candidate. Compilation
and verification diagnostics are preserved. Only a valid edit followed by actual
Verus success counts as repaired. Saved results/responses support resume without
new inference; changed frozen inputs/code/tools/adapter block resume.

## Feedback and prompts

Both arms use the same task and solver-interpretation instructions. Solver Needs
receives the old detailed AX/INST-forall/INST-witness/NLA/FUEL/Other guidance, updated
to THREE proposals. VerusBench receives exact JSON and region-kind instructions.
The SAFE internals guide is included with its full-file output instruction removed.
The fine-tuned model was trained on full files, so invalid JSON/format errors are
important measured outcomes, not automatically repaired by a second LLM.

With-internals: up to 24,576 tokens, 50 groups x 3 instances, seven statistics,
first up to three captured SAT/UNKNOWN queries, concordant diagnostic replays only.
32,768 total context with 4,096 reserved for output; no program/diagnostic clipping.
Quantifier selection accounts for the localized prompt/catalogue/site listing,
so the actual payload may be smaller than in full-file evaluation. No new extra
internals blocks. Without-internals receives no solver payload. In VerusBench,
feedback starts at localized repair 1 / overall proposal 2. Solver Needs receives
feedback before its first action. Raw initial replay events are reused when saved;
fresh accepted candidates use fresh verification/capture and bounded replays.

## Caveats and checks

Training-overlap flags are inherited from actual training-ID screening in the
source evaluation. Full totals and unflagged subtotals are retained; this does not
certify semantic independence of unflagged variants. Missing IDs and initial
eligibility/exclusion IDs are explicit in the JSON. No result is fabricated for
pending tasks. Context-budget failures are distinct from proof failures.

Local tests check paired seeds, slot/no-op handling, v2 proof insertions, exactly
two new VerusBench repairs after the shared initial, excluded editor cases,
unchanged frozen inputs and no repeated inference after resume. GPU inference,
actual verifier compatibility and performance remain to be checked on the cluster.
Only new package/scripts are added: the scientific configuration/fingerprint of
the running full-file evaluations is not changed by these additions.
