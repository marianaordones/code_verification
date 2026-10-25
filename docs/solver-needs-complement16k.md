# Complementary input-quantifier feedback: first 100 tasks

This paired study compares **base24k only** against **the same base24k plus up to 16k complementary tokens**. Both arms use Qwen2.5-Coder-14B-Instruct, a 61,440-token total context, a 4,096-token output reservation, three total proposals, the frozen first 100 IDs, and the original candidate and sampling seeds. The base has at most 50 groups and three instantiations per group. No full SMT query is sent.

The complement includes at most **20 input quantified formulas without observed events**, prioritized by candidate annotations/definitions and operations near the failure (at most two operation-related library formulas). Each includes its full formula, kind, bound variables, unique qid, checksum, and zero exact-formula/unique-outer-qid event counts. Explicit triggers appear within the formula. Up to two input ground-term examples per trigger-root symbol provide context, not a matching diagnosis. The package also reports inventory coverage, callback errors, selection omissions, and full callback counts for groups already displayed in the base (referenced by query/group index, without repeating formulas). Counts continue after instance-sampling caps.

An ambiguous/missing input qid, incomplete inventory, or callback error prevents inclusion as a formula without observed events. These are bounded diagnostic replays, not the original Verus search. Absence of events does not establish elimination, inactivity, or the cause of failure. Native profile columns and generic theory clauses are not included. The explanatory prompt appendix is `prompts/solver-needs/complement.txt` and is identical in both arms.

## Run on the cluster

From the repository root, after updating `solver_needs_study/`, `repair_study/`, `diagnostics/`, `configs/`, `prompts/`, `scripts/`, and `tests/`:

```bash
bash scripts/submit_solver_needs_complement16k.sh \
  results/solver-needs-qwen14b-100-internals24k/seed-20261018
```

Pass an absolute source path instead if the completed original 24k/50x3 study is elsewhere. The source must include frozen inputs, saved queries, manifests, and completed per-arm results. Preparation validates source hashes/settings, keeps the original candidate/query bytes, and performs **new shared initial diagnostic replays** to collect the input inventory and exact event counters. It does not rerun the initial Verus call or reuse an old trace while pretending it contains these new fields. Both arms' first proposals use the same new saved replay evidence and byte-identical base feedback. Later candidates and replays may differ after model actions diverge.

The launcher submits CPU preparation, one GPU job running both arms, and comparison with dependencies and the existing `high` QoS. Existing GPU resources remain one GPU / 64G host RAM. The larger context requires sufficient GPU KV-cache capacity; this code does not test remote GPU availability. Keep a separate output directory for this experiment.

Default output: `results/solver-needs-qwen14b-100-complement16k/seed-20261018/study/`. Read `comparison.md` and `comparison.json` there. For compatibility with the runner, directory **with_internals means base + complement**, and **without_internals means base only**; this is stated in both reports. It is not a no-internals control.

Inspect `inputs/ID/feedback.json` and per-attempt `exposure.json` for the actual package, selected/omitted counts, and separate block token counts; `request.json` records the actual messages. The 16k cap and the remaining total context are enforced on the serialized package and actual chat template. Whole complementary formulas are omitted when necessary; source/base feedback is never silently truncated. The common prompt includes the same interpretation guidance in both arms. Base selection does not depend on complementary selection.

Updating runner files changes implementation hashes. Finish any active jobs before updating their checkout; old result files remain intact, but their resumability under the old fingerprint requires the old code.

This comparison tests the additional selected information **and its additional token budget**. A positive result alone would not separate those two effects; an equal-token additional-old-information control can be considered later.
