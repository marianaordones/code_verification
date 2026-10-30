#!/usr/bin/env bash
set -Eeuo pipefail
dataset="${1:-data/safe/sft_safe_25k.json}"
output="${2:-results/safe-internals-pilot1000-attrs-v2/seed-20261018}"
[[ -f "$dataset" ]] || { echo "Missing SAFE JSON: $dataset" >&2; exit 2; }
mkdir -p logs
job="$(sbatch --parsable --job-name=safe-internals-1000 scripts/slurm/safe_internals_pilot.slurm \
    "$dataset" "$output" collect configs/safe-internals-pilot1000.json)"
echo "CPU collection job: ${job%%;*} (1000 examples, including the original 200, all rerun)"
echo "Report: $output/report.md"
echo "Validated positive views: $output/exports/validated/ (still unsplit)"
