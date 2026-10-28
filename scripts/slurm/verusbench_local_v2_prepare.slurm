#!/usr/bin/env bash
#SBATCH --job-name=verus-local-v2-prepare
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from repository root}"
python3 -m baseline.verusbench_local_v2 prepare --source "${1:?Source run}" --output "${2:?Output study}"
