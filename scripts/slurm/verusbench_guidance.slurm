#!/usr/bin/env bash
#SBATCH --job-name=vb-oracle-guidance
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:L40S:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
trap 'echo "GUIDANCE_ERROR job=${SLURM_JOB_ID:-local} line=$LINENO exit=$?" >&2' ERR
cd "${SLURM_SUBMIT_DIR:?}"
echo GUIDANCE_STAGE=runtime
benchmark=verusbench
if [[ -f cluster.env ]]; then source ./cluster.env; fi
export CLUSTER_REQS="$SLURM_SUBMIT_DIR/requirements-cluster.txt" VLLM_USE_V1=0
source scripts/cluster/setup_runtime.sh
source scripts/cluster/setup_safe_rust.sh
source scripts/cluster/stage_safe_sft_eval.sh
nvidia-smi
arguments=("$@")
output=""
while [[ $# -gt 0 ]]; do
    case "$1" in --output) output="${2:?}"; shift 2 ;; *) shift ;; esac
done
[[ -n "$output" ]] || { echo '--output required' >&2; exit 2; }
echo GUIDANCE_STAGE=revalidate_inputs_and_references
python -m guidance_study.evaluate prepare "${arguments[@]}"
echo GUIDANCE_STAGE=paired_inference
status=0
python -m guidance_study.evaluate run --output "$output" || status=$?
python -m guidance_study.evaluate report --output "$output"
exit "$status"
