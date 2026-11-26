#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
dataset=data/verusbench-guidance-v1
output=results/verusbench-guidance-base-v1
adapter=""
proposals=3
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dataset) dataset="${2:?}"; shift 2 ;;
        --output) output="${2:?}"; shift 2 ;;
        --adapter) adapter="${2:?}"; shift 2 ;;
        --proposals) proposals="${2:?}"; shift 2 ;;
        *) echo 'Use --dataset DIR --output DIR [--adapter DIR] [--proposals 1|2|3]' >&2; exit 2 ;;
    esac
done
[[ -s "$dataset/manifest.json" ]] || { echo "Missing subset: $dataset/manifest.json" >&2; exit 2; }
args=(--dataset "$dataset" --output "$output" --proposals "$proposals")
if [[ -n "$adapter" ]]; then
    [[ -s "$adapter/adapter_model.safetensors" ]] || { echo 'Missing adapter weights' >&2; exit 2; }
    args+=(--adapter "$adapter")
fi
mkdir -p logs
sbatch --partition=high_performance --qos=high --gres="gpu:${EVAL_GPU_TYPE:-L40S}:1" \
    scripts/slurm/verusbench_guidance.slurm "${args[@]}"
