#!/usr/bin/env bash
#SBATCH --job-name=verus-14b-v2-50
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=1-00:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
PROJECT_ROOT="${SLURM_SUBMIT_DIR:?Submit from the repository root}"
cd "$PROJECT_ROOT"
source scripts/cluster/job_init.sh
bash scripts/run_experiment.sh pilot14-50
