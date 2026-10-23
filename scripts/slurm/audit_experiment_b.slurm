#!/usr/bin/env bash
#SBATCH --job-name=verus-b-audit
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
PROJECT_ROOT="${SLURM_SUBMIT_DIR:?Submit from the repository root}"
cd "$PROJECT_ROOT"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
# Reuse the experiment's Python package cache, without GPU preflight or model loading.
source scripts/cluster/setup_runtime.sh
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python -m diagnostics.b_audit \
    --run "${1:-results/qwen25coder14b-b-150/seed-20261018/full/instruct}" \
    --output "${2:-analysis/b-audit-${SLURM_JOB_ID}}"
