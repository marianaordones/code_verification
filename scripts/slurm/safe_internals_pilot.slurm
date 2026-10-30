#!/usr/bin/env bash
#SBATCH --job-name=safe-internals-200
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=1-00:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from repository root}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
source scripts/cluster/setup_safe_cpu.sh
output="${2:-results/safe-internals-pilot200/seed-20261018}"
if [[ "${3:-collect}" == report ]]; then
    python -m safe_internals report --output "$output"
    exit 0
fi
source scripts/cluster/setup_safe_rust.sh
source scripts/cluster/stage_tools.sh
if [[ -f "$tools_bundle_dir/tools-native.json" ]]; then
    export SAFE_TOOLS_MANIFEST="$PROJECT_ROOT/$tools_bundle_dir/tools-native.json"
    if [[ "$tools_bundle_dir" = /* ]]; then export SAFE_TOOLS_MANIFEST="$tools_bundle_dir/tools-native.json"; fi
fi
source scripts/cluster/setup_z3_internals.sh
python -m unittest discover -s tests -p 'test_safe_internals.py' -v
python -m safe_internals prepare --dataset "${1:?SAFE JSON path}" --output "$output" \
    --config "${4:-configs/safe-internals-pilot200.json}"
python -m safe_internals collect --output "$output" --workers 2
