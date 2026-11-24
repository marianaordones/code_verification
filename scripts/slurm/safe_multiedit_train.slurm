#!/usr/bin/env bash
#SBATCH --job-name=safe-multiedit-sft
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:A100:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=3-00:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
trap 'echo "SAFE_MULTIEDIT_ERROR job=${SLURM_JOB_ID:-local} line=$LINENO exit=$?" >&2' ERR
cd "${SLURM_SUBMIT_DIR:?}"
echo "SAFE_MULTIEDIT_STAGE=training_runtime job=${SLURM_JOB_ID:-local}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
source scripts/cluster/setup_safe_sft.sh
nvidia-smi
python scripts/train_safe_multiedit.py "$@"
