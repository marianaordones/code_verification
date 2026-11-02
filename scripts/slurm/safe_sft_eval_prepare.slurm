#!/usr/bin/env bash
#SBATCH --job-name=safe-eval-prepare
#SBATCH --partition=new_p_general
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
benchmark="${1:?benchmark}"; shift
if [[ -f cluster.env ]]; then source ./cluster.env; fi
source scripts/cluster/setup_safe_cpu.sh
source scripts/cluster/setup_safe_rust.sh
source scripts/cluster/stage_safe_sft_eval.sh
source scripts/cluster/setup_z3_internals.sh
python -m sft_eval prepare --benchmark "$benchmark" "$@"
