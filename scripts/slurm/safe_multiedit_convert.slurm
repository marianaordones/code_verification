#!/usr/bin/env bash
#SBATCH --job-name=safe-multiedit-convert
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
trap 'echo "SAFE_MULTIEDIT_ERROR job=${SLURM_JOB_ID:-local} line=$LINENO exit=$?" >&2' ERR
cd "${SLURM_SUBMIT_DIR:?}"
echo "SAFE_MULTIEDIT_STAGE=cpu_runtime job=${SLURM_JOB_ID:-local}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
source scripts/cluster/setup_safe_cpu.sh
if [[ "${1:-}" == --report ]]; then
    shift
    python -m localized_sft.evaluate report "$@"
else
    python -m unittest discover -s tests -p test_safe_multiedit.py -v
    echo SAFE_MULTIEDIT_STAGE=convert
    python -m localized_sft.convert "$@"
fi
