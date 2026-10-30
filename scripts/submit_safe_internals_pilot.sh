#!/usr/bin/env bash
set -Eeuo pipefail
dataset="${1:-data/safe/sft_safe_25k.json}"
output="${2:-results/safe-internals-pilot200/seed-20261018}"
if [[ ! -f "$dataset" ]]; then
    echo "SAFE dataset missing: $dataset" >&2
    echo 'Copy sft_safe_25k (1).json here, or pass its existing cluster path as argument 1.' >&2
    exit 2
fi
mkdir -p logs
job="$(sbatch --parsable scripts/slurm/safe_internals_pilot.slurm "$dataset" "$output")"
echo "CPU collection job: ${job%%;*}"
echo "Report: $output/report.md"
echo 'No GPU requested; only tokenizer files are downloaded.'
