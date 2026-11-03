#!/usr/bin/env bash
#SBATCH --job-name=safe-local-report
#SBATCH --partition=high_performance
#SBATCH --gres=gpu:L40S:1
#SBATCH --qos=high
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
export PYTHONNOUSERSITE=1
python3 -m sft_local_eval report "$@"
