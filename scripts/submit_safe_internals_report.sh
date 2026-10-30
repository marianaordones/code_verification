#!/usr/bin/env bash
set -Eeuo pipefail
output="${1:-results/safe-internals-pilot200/seed-20261018}"
[[ -f "$output/manifest.json" ]] || { echo "Missing manifest in $output" >&2; exit 2; }
mkdir -p logs
sbatch --job-name=safe-pilot-report --cpus-per-task=2 --mem=4G --time=00:20:00 \
    scripts/slurm/safe_internals_pilot.slurm "" "$output" report
