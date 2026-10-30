#!/usr/bin/env bash
set -Eeuo pipefail
dataset="${1:-data/safe/sft_safe_25k.json}"
output="${2:-results/safe-internals-second1000-attrs-v2/seed-20261018}"
[[ -f "$dataset" ]] || { echo "Missing SAFE JSON: $dataset" >&2; exit 2; }
mkdir -p logs
job="$(sbatch --parsable scripts/slurm/safe_internals_second1000.slurm "$dataset" "$output")"
echo "Independent CPU collection job: ${job%%;*} (1000 NEW input programs; no GPU requested)"
echo "Report: $output/report.md"
echo "Validated positive views: $output/exports/validated/"
