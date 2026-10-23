#!/usr/bin/env bash
# Common initialization sourced by every Slurm entry point.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Source this file from a Slurm job." >&2
    exit 2
fi
PROJECT_ROOT="${SLURM_SUBMIT_DIR:?Submit from the repository root}"
cd "$PROJECT_ROOT"
if [[ -z "${CUDA_VISIBLE_DEVICES:-}" || "${CUDA_VISIBLE_DEVICES:-}" == NoDevFiles || "${CUDA_VISIBLE_DEVICES:-}" == -1 ]]; then
    echo "SLURM did not assign CUDA_VISIBLE_DEVICES; refusing to install/run without a GPU allocation." >&2
    return 25
fi
if [[ -f cluster.env ]]; then source ./cluster.env; fi
export CLUSTER_REQS="${CLUSTER_REQS:-${PROJECT_ROOT}/requirements-cluster.txt}"
source scripts/cluster/setup_runtime.sh
echo "date=$(date --iso-8601=seconds)"
echo "job_id=${SLURM_JOB_ID:-local}"
echo "node=$(hostname)"
echo "commit=$(git rev-parse HEAD 2>/dev/null || echo unavailable)"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-<unset>}"
command -v nvidia-smi >/dev/null || { echo "nvidia-smi missing on the assigned compute node." >&2; return 25; }
nvidia-smi --query-gpu=index,name,driver_version,memory.used,memory.total --format=csv,noheader
python scripts/cluster/preflight.py
mkdir -p logs
cp "$PROJECT_LIBS/requirements-resolved.txt" "logs/requirements-${SLURM_JOB_ID:-local}.txt"

# Tool paths are staged by run_experiment.sh; never load stale node-local paths
# or execute binaries directly from the shared filesystem here.
