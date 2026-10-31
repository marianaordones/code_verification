#!/usr/bin/env bash
#SBATCH --job-name=safe-generation-check
#SBATCH --partition=new_p_general
#SBATCH --qos=high
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=2-00:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
source scripts/cluster/setup_safe_cpu.sh
source scripts/cluster/setup_safe_rust.sh
source scripts/cluster/stage_tools.sh
python scripts/validate_safe_generation.py "$@"
