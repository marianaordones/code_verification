#!/usr/bin/env bash
# Two paired experiments; collect the shared initial five-instance pool once.
set -Eeuo pipefail
root="${1:-results/solver-needs-qwen14b-100-internals32k-samples/seed-20261018}"
source_study="${2:-results/solver-needs-qwen14b-100-internals24k/seed-20261018}"
if [[ ! -f "$source_study/manifest.json" ]]; then
    echo "Missing completed 24k source manifest: $source_study/manifest.json" >&2
    exit 2
fi
mkdir -p logs
study_a="$root/80x3"
study_b="$root/50x5"
pool="$root/shared-initial-events"
prepare_id="$(sbatch --parsable scripts/slurm/solver_needs_32k_samples_prepare.slurm "$source_study" "$study_a" "$study_b" "$pool")"
prepare_id="${prepare_id%%;*}"
run_a="$(sbatch --parsable --job-name=solver-needs-32k-80x3 --dependency="afterok:$prepare_id" scripts/slurm/solver_needs_run.slurm "$study_a")"
run_a="${run_a%%;*}"
run_b="$(sbatch --parsable --job-name=solver-needs-32k-50x5 --dependency="afterok:$prepare_id" scripts/slurm/solver_needs_run.slurm "$study_b")"
run_b="${run_b%%;*}"
report_a="$(sbatch --parsable --dependency="afterany:$run_a" scripts/slurm/solver_needs_compare.slurm "$study_a")"
report_b="$(sbatch --parsable --dependency="afterany:$run_b" scripts/slurm/solver_needs_compare.slurm "$study_b")"
echo "Shared CPU preparation: $prepare_id"
echo "80 groups x 3 instances: GPU $run_a; report ${report_a%%;*}; $study_a/comparison.md"
echo "50 groups x 5 instances: GPU $run_b; report ${report_b%%;*}; $study_b/comparison.md"
echo "Shared refreshed initial replay evidence: $pool"
