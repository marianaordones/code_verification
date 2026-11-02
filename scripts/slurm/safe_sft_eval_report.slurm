#!/usr/bin/env bash
#SBATCH --job-name=safe-eval-report
#SBATCH --partition=new_p_general
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
python3 -m sft_eval report "$@"
