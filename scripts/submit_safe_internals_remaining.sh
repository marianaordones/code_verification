#!/usr/bin/env bash
set -Eeuo pipefail
dataset="${1:-data/safe/sft_safe_25k.json}"
parent="${2:-results/safe-internals-remaining-attrs-v2}"
# Argument 3 optionally resumes one batch instead of submitting all four.
batch_filter="${3:-all}"
case "$batch_filter" in all|a|b|c|d) ;; *) echo 'Argument 3 must be all, a, b, c or d' >&2; exit 2 ;; esac
[[ -f "$dataset" ]] || { echo "Missing SAFE JSON: $dataset" >&2; exit 2; }
mkdir -p logs
for batch in a b c d; do
    [[ "$batch_filter" == all || "$batch_filter" == "$batch" ]] || continue
    output="$parent/$batch/seed-20261018"
    job="$(sbatch --parsable --job-name="safe-internals-rest-$batch" scripts/slurm/safe_internals_remaining.slurm \
        "$batch" "$dataset" "$output")"
    echo "Batch $batch (2942 repair rows), independent CPU job: ${job%%;*}"
    echo "Report: $output/report.md"
done
echo 'Four new shards cover the 11768 remaining repair rows; the first 2000 are excluded.'
echo 'No GPU is requested. Keep shared collector code unchanged while jobs run.'
