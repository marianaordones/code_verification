#!/usr/bin/env bash
#SBATCH --job-name=safe-local-eval
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=2-00:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
benchmark="${1:?benchmark}"; shift
if [[ -f cluster.env ]]; then source ./cluster.env; fi
export CLUSTER_REQS="$SLURM_SUBMIT_DIR/requirements-cluster.txt" VLLM_USE_V1=0
source scripts/cluster/setup_runtime.sh
source scripts/cluster/setup_safe_rust.sh
source scripts/cluster/stage_safe_sft_eval.sh
source scripts/cluster/setup_z3_internals.sh
nvidia-smi
python -m sft_local_eval run "$@"
