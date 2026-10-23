#!/usr/bin/env bash
#SBATCH --job-name=verus-ablation-prepare
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from repository root}"
python3 -m unittest discover -s tests -p test_local_ablation.py -v
python3 -m local_ablation prepare --source-study "${1:?Frozen source study}" --study "${2:?Output study}"
