#!/usr/bin/env bash
# Submit from the repository root. One GPU runs both paired arms.
set -Eeuo pipefail
source_study="${1:-results/paired-repair-study-48k/all-eligible}"
study="${2:-results/localized-internals-ablation-48k/seed-20261018}"
[[ -f "$source_study/manifest.json" ]] || { echo "Frozen study not found: $source_study/manifest.json" >&2; exit 2; }
mkdir -p logs
prepare_id="$(sbatch --parsable scripts/slurm/local_ablation_prepare.slurm "$source_study" "$study")"
prepare_id="${prepare_id%%;*}"
run_id="$(sbatch --parsable --dependency="afterok:${prepare_id}" scripts/slurm/local_ablation_run.slurm "$study")"
run_id="${run_id%%;*}"
compare_id="$(sbatch --parsable --dependency="afterany:${run_id}" scripts/slurm/local_ablation_compare.slurm "$study")"
echo "Preparation: $prepare_id"
echo "Paired localized arms on one GPU: $run_id"
echo "Comparison: ${compare_id%%;*}"
echo "Report: $study/comparison.md"
