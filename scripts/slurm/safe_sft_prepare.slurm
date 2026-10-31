#!/usr/bin/env bash
#SBATCH --job-name=safe-sft-prepare
#SBATCH --partition=new_p_general
#SBATCH --qos=high
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
source scripts/cluster/setup_safe_cpu.sh
python scripts/safe_sft_data.py "$@"
