# Comparing the complete 12k/20x3 and 24k/50x3 runs

Run from the `code_verification_git` repository root on the cluster:

```bash
python3 scripts/compare_solver_needs_three_proposals.py
```

No GPU, packages, model, solver, or Slurm allocation is needed. This script uses Python's standard library and does not import the experiment runner. It can therefore read saved records even when `compare` failed because the working code changed. It does not alter result files or their manifests, and does not certify that prompts stayed unchanged while jobs ran.

Defaults:

- Previous 100: sibling `code_verification/results/solver-needs-qwen14b-100/seed-20261018`.
- Previous 362: sibling `code_verification/results/solver-needs-qwen14b-remaining362/seed-20261018`.
- Current 100: `results/solver-needs-qwen14b-100-internals24k/seed-20261018` (the original 24k/50x3 run, not the complementary-internals run).
- Current 362: `results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018`.

Override paths if necessary:

```bash
python3 scripts/compare_solver_needs_three_proposals.py \
  --previous ../code_verification/results/solver-needs-qwen14b-100/seed-20261018 \
             ../code_verification/results/solver-needs-qwen14b-remaining362/seed-20261018 \
  --current-first100 results/solver-needs-qwen14b-100-internals24k/seed-20261018 \
  --current-remaining362 results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018
```

Results are written to `analysis/solver-needs-full-three-proposals/`:

- `report.md`: totals for old 462, new 462, and new 362 alone.
- `comparison.json`: cumulative successes at proposals 1, 2, and 3, categories, exclusive wins, missing cases, and IDs solved only after proposal 3. Source manifest hashes/configurations are retained for provenance.
- `tables.tex`: English LaTeX tables for the overall comparison and the category comparison; requires `\usepackage{booktabs}`. Upload this file to Overleaf and use `\input{tables.tex}`, or paste its contents.

The script reads one-based per-proposal records; it never uses final task success to credit a fourth-proposal solution within three proposals. If a task summary is missing, it reads saved `attempt_*/result.json` files. Pending cases remain explicit and prevent generation of final LaTeX tables. Both complete configurations must contain exactly the same 462 IDs and matching categories/initial eligibility. Feedback budgets and sampling caps are checked; current code hashes are deliberately not checked.

This compares a 24k/50x3 configuration assembled from its original 100-task run plus its 362-task continuation. Do not substitute the newer 24k+16k complement experiment: its control also receives internals and answers a different question.
