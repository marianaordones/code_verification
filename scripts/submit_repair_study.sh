#!/usr/bin/env bash
# Run from the project root on the cluster. Two independent one-GPU jobs.
set -Eeuo pipefail
source_run="${1:-results/qwen25coder14b-c-internals-150/seed-20261018/full/instruct}"
study="${2:-results/paired-repair-study-48k/seed-20261018}"
count="${3:-30}"
[[ -f "$source_run/run.json" ]] || { echo "Source run not found: $source_run" >&2; exit 2; }
mkdir -p logs
prepare_id="$(sbatch --parsable scripts/slurm/repair_study_prepare.slurm "$source_run" "$study" "$count")"
prepare_id="${prepare_id%%;*}"
full_id="$(sbatch --parsable --dependency="afterok:${prepare_id}" --job-name=verus-repair-full \
    scripts/slurm/repair_study_run.slurm "$study" full)"
full_id="${full_id%%;*}"
local_id="$(sbatch --parsable --dependency="afterok:${prepare_id}" --job-name=verus-repair-local \
    scripts/slurm/repair_study_run.slurm "$study" local)"
local_id="${local_id%%;*}"
compare_id="$(sbatch --parsable --dependency="afterany:${full_id}:${local_id}" \
    scripts/slurm/repair_study_compare.slurm "$study")"
echo "Preparation: $prepare_id"
echo "Experiment 1 (full file): $full_id"
echo "Experiment 2 (localized edit): $local_id"
echo "Comparison: ${compare_id%%;*}"
echo "Report: $study/comparison.md"
