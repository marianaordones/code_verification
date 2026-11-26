#!/usr/bin/env bash
#SBATCH --job-name=vb-guidance-more
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
trap 'echo "GUIDANCE_MORE_ERROR job=${SLURM_JOB_ID:-local} line=$LINENO exit=$?" >&2' ERR
cd "${SLURM_SUBMIT_DIR:?}"
echo GUIDANCE_MORE_STAGE=cpu_runtime
benchmark=verusbench
if [[ -f cluster.env ]]; then source ./cluster.env; fi
source scripts/cluster/setup_safe_cpu.sh
source scripts/cluster/setup_safe_rust.sh
source scripts/cluster/stage_safe_sft_eval.sh
echo GUIDANCE_MORE_STAGE=validate_references
python -m guidance_more validate "$@"
