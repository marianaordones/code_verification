#!/usr/bin/env bash
#SBATCH --job-name=safe-local-eval
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:L40S:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=2-00:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
benchmark="${1:?benchmark}"; shift
source_study=""
output=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --source) source_study="${2:?source path}"; shift 2 ;;
        --output) output="${2:?output path}"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[[ -n "$source_study" && -n "$output" ]] || { echo '--source and --output required' >&2; exit 2; }
if [[ -f cluster.env ]]; then source ./cluster.env; fi
export CLUSTER_REQS="$SLURM_SUBMIT_DIR/requirements-cluster.txt" VLLM_USE_V1=0
source scripts/cluster/setup_runtime.sh
source scripts/cluster/setup_safe_rust.sh
source scripts/cluster/stage_safe_sft_eval.sh
source scripts/cluster/setup_z3_internals.sh
nvidia-smi
echo 'SAFE_LOCAL_STAGE=prepare'
python -m sft_local_eval prepare --source "$source_study" --output "$output"
echo 'SAFE_LOCAL_STAGE=run'
run_status=0
python -m sft_local_eval run --output "$output" || run_status=$?
echo 'SAFE_LOCAL_STAGE=report'
python -m sft_local_eval report --output "$output"
exit "$run_status"
