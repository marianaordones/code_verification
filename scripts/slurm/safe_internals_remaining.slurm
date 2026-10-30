#!/usr/bin/env bash
#SBATCH --job-name=safe-internals-rest
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=1-00:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
stage=entry
trap 'exit_code=$?; printf "SAFE_REMAINING_ERROR job=%s stage=%s file=%s line=%s exit=%s\n" "${SLURM_JOB_ID:-unknown}" "$stage" "${BASH_SOURCE[0]:-unknown}" "$LINENO" "$exit_code" >&2' ERR
printf 'SAFE_REMAINING_START job=%s host=%s cwd=%s\n' "${SLURM_JOB_ID:-unknown}" "${HOSTNAME:-unknown}" "$PWD"
stage=working_directory
cd "${SLURM_SUBMIT_DIR:?Submit from repository root}"
batch="${1:?Batch a/b/c/d}"
case "$batch" in a|b|c|d) ;; *) echo 'Expected batch a, b, c or d' >&2; exit 2 ;; esac
dataset="${2:?SAFE dataset}"
output="${3:?Output directory}"
printf 'batch=%s dataset=%s output=%s\n' "$batch" "$dataset" "$output"
stage=cluster_environment
if [[ -f cluster.env ]]; then source ./cluster.env; fi
stage=system_commands
for required_command in flock mktemp sha256sum awk stat df tar cp chmod; do
    if ! command -v "$required_command" >/dev/null; then
        echo "Missing system command on ${HOSTNAME:-node}: $required_command" >&2
        exit 1
    fi
done
stage=cpu_runtime
echo "SAFE_STAGE=$stage"
source scripts/cluster/setup_safe_cpu.sh
stage=rust
echo "SAFE_STAGE=$stage"
source scripts/cluster/setup_safe_rust.sh
stage=native_tools
echo "SAFE_STAGE=$stage"
source scripts/cluster/stage_tools.sh
if [[ -f "$tools_bundle_dir/tools-native.json" ]]; then
    export SAFE_TOOLS_MANIFEST="$PROJECT_ROOT/$tools_bundle_dir/tools-native.json"
    if [[ "$tools_bundle_dir" = /* ]]; then export SAFE_TOOLS_MANIFEST="$tools_bundle_dir/tools-native.json"; fi
fi
stage=z3_api
echo "SAFE_STAGE=$stage"
source scripts/cluster/setup_z3_internals.sh
stage=tests
echo "SAFE_STAGE=$stage"
python -m unittest discover -s tests -p 'test_safe*.py' -v
stage=prepare
echo "SAFE_STAGE=$stage"
python scripts/prepare_safe_internals_remaining.py --dataset "$dataset" --output "$output" --batch "$batch"
stage=collect
echo "SAFE_STAGE=$stage"
python -m safe_internals collect --output "$output" --workers 2
echo 'SAFE_REMAINING_FINISHED successfully'
