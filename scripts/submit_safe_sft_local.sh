#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
which="${1:-all}"
sources="${2:-results/safe-sft-eval-v1}"
outputs="${3:-results/safe-sft-local-v1}"
case "$which" in all|verusbench|solver-needs) ;; *) echo 'Use all, verusbench or solver-needs' >&2; exit 2 ;; esac
mkdir -p logs "$outputs"
sources="$(cd "$sources" && pwd -P)"
outputs="$(cd "$outputs" && pwd -P)"
for benchmark in verusbench solver-needs; do
    [[ "$which" == all || "$which" == "$benchmark" ]] || continue
    [[ -s "$sources/$benchmark/manifest.json" ]] || { echo "Missing full-file source manifest: $sources/$benchmark" >&2; exit 2; }
done
receipt="logs/safe-local-submission-$(date +%Y%m%dT%H%M%S)-$$.tsv"
printf 'benchmark\tjob\toutput\n' > "$receipt"
for benchmark in verusbench solver-needs; do
    [[ "$which" == all || "$which" == "$benchmark" ]] || continue
    run="$(sbatch --parsable --partition=high_performance --qos=high --gres=gpu:L40S:1 \
        --job-name="safe-local-$benchmark" scripts/slurm/safe_sft_local_all.slurm \
        "$benchmark" --source "$sources/$benchmark" --output "$outputs/$benchmark")"
    run="${run%%;*}"
    printf '%s\t%s\t%s\n' "$benchmark" "$run" "$outputs/$benchmark" >> "$receipt"
    echo "$benchmark: job=$run (prepare + run + report, high_performance/L40S)"
done
echo "Submission record: $receipt"
