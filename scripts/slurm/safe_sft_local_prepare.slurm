#!/usr/bin/env bash
#SBATCH --job-name=safe-local-prepare
#SBATCH --partition=high_performance
#SBATCH --gres=gpu:L40S:1
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
benchmark="${1:?benchmark}"; shift
if [[ -f cluster.env ]]; then source ./cluster.env; fi
source scripts/cluster/setup_safe_cpu.sh
source scripts/cluster/setup_safe_rust.sh
source scripts/cluster/stage_safe_sft_eval.sh
python -m sft_local_eval prepare "$@"
