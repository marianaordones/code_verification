#!/usr/bin/env bash
#SBATCH --job-name=verus-z3-exposure
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
PROJECT_ROOT="${SLURM_SUBMIT_DIR:?Submit from the repository root}"
cd "$PROJECT_ROOT"
source scripts/cluster/job_init.sh
source scripts/cluster/stage_tools.sh
export Z3_PROBE_WORK="${NATIVE_WORKSPACE:?}/z3-probe"
mkdir -p "$Z3_PROBE_WORK"

# Separate native installation: never change the inference environment or the
# original Verus/Z3 binaries. API callback extraction is optional if offline.
if [[ "${Z3_PROBE_INSTALL_PYTHON:-1}" == 1 ]]; then
    if python -m pip install --no-deps --only-binary=:all: \
        --target "$Z3_PROBE_WORK/z3py" z3-solver==4.12.5.0 \
        > "logs/z3-probe-install-${SLURM_JOB_ID:-local}.log" 2>&1; then
        export PYTHONPATH="$Z3_PROBE_WORK/z3py:${PYTHONPATH:-}"
    else
        echo "Optional Z3 Python installation failed; CLI capture remains available. See install log."
    fi
fi

source_run="${1:-results/qwen25coder14b-v3-150/seed-20261018/full/instruct}"
output="${2:-results/z3-exposure/job-${SLURM_JOB_ID:?}}"
python -m diagnostics.z3_exposure --source-run "$source_run" --output "$output"
