#!/usr/bin/env bash
#SBATCH --job-name=safe-training-audit
#SBATCH --partition=new_p_general
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=02:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
python3 scripts/audit_safe_training.py "$@"
