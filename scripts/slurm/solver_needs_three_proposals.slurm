#!/usr/bin/env bash
#SBATCH --job-name=solver-needs-three
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:15:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit through scripts/submit_solver_needs_three_proposals.sh}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
# Standard-library analysis: no package cache, CUDA, Verus, or model initialization.
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
analysis_python=""
for candidate in "${CLUSTER_PYTHON:-}" python3.12 python3.11 python3; do
    [[ -n "$candidate" ]] || continue
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
    [[ -n "$resolved" ]] || continue
    if "$resolved" -c 'import sys; assert sys.version_info >= (3, 9)' 2>/dev/null; then
        analysis_python="$resolved"
        break
    fi
done
if [[ -z "$analysis_python" ]]; then
    echo "Python >= 3.9 unavailable on compute node; set CLUSTER_PYTHON in cluster.env." >&2
    exit 2
fi
echo "Analysis interpreter: $analysis_python"
"$analysis_python" scripts/compare_solver_needs_three_proposals.py "$@"
