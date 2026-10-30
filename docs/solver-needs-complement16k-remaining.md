# Base24k + complement16k: remaining 362, single arm

Runs only the augmented package on the frozen 362 tasks outside the initial 100. No base-only control is scheduled. Uses the unchanged complement prompt, model revision, seed, 61,440 context tokens, 4,096 reserved output tokens, base24,576 / 50 groups / three instances, complement16,384 / 20 formulas without observed events, and three total proposals.

Finish active jobs before updating their checkout. Update `solver_needs_study/`, `configs/`, `scripts/`, and `tests/`, then submit from the repository root:

```bash
bash scripts/submit_solver_needs_complement16k_remaining.sh
```

Default source: `results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018`. This must be the completed remaining-362 base24k/50x3 study, not the old 12k/20x3 run. If elsewhere, pass the source directory as argument 1; optional argument 2 sets the output parent:

```bash
bash scripts/submit_solver_needs_complement16k_remaining.sh \
  /home/mariana.soares/code_verification/results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018
```

Preparation validates source IDs, settings, hashes, tool identities and first common prompts, reusing original candidate/query bytes without new initial Verus calls. New shared initial diagnostic replays collect input inventories and exact counters. It reads both arms of the old source for validation but generates NO base-only proposals in the new run. Source results remain unchanged. Later replays describe the evolving augmented candidate. See `solver-needs-complement16k.md` for payload semantics and replay limitations.

Submits CPU preparation, one GPU job and dependent reporting with the existing high QoS/resources. The generic submission message still calls the GPU job paired; `single_arm` in the saved configuration controls execution and the report explicitly states no control was run.

Default reports:

```text
results/solver-needs-qwen14b-remaining362-complement16k-single/seed-20261018/study/comparison.md
results/solver-needs-qwen14b-remaining362-complement16k-single/seed-20261018/study/comparison.json
```

The only result arm is `with_internals`, meaning base24k + complement16k. Reports include successes through each proposal, categories, missing tasks, errors and tokens. No paired gains are calculated and earlier 100-task results are not automatically combined. All IDs, requests, exposure measurements and replay evidence remain saved.
