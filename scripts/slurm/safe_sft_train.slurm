#!/usr/bin/env bash
#SBATCH --job-name=safe-sft
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
if [[ -f cluster.env ]]; then source ./cluster.env; fi
# Set before importing torch. Helps fragmentation; does not add GPU capacity.
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
source scripts/cluster/setup_safe_sft.sh
nvidia-smi
python scripts/train_safe_sft.py "$@"
