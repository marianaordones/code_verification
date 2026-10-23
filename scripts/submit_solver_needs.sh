#!/usr/bin/env bash
set -Eeuo pipefail
study="${1:-results/solver-needs-qwen14b-100/seed-20261018}"
tasks="${2:-100}"
selection="${3:-configs/solver-needs-tasks100.json}"
mkdir -p logs
prepare_id="$(sbatch --parsable scripts/slurm/solver_needs_prepare.slurm "$study" "$tasks" "$selection")"
prepare_id="${prepare_id%%;*}"
run_id="$(sbatch --parsable --dependency="afterok:${prepare_id}" scripts/slurm/solver_needs_run.slurm "$study")"
run_id="${run_id%%;*}"
compare_id="$(sbatch --parsable --dependency="afterany:${run_id}" scripts/slurm/solver_needs_compare.slurm "$study")"
echo "Preparation (published screens; only stripped candidates executed): $prepare_id"
echo "Paired Qwen experiment (one GPU, both arms): $run_id"
echo "Comparison: ${compare_id%%;*}"
echo "Report: $study/comparison.md"
