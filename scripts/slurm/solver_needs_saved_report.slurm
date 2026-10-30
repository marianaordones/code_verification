#!/usr/bin/env bash
#SBATCH --job-name=solver-needs-saved-cmp
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from repository root}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
report_python=""
for candidate in "${CLUSTER_PYTHON:-}" python3.12 python3.11 python3; do
    [[ -n "$candidate" ]] || continue
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; assert sys.version_info >= (3, 9)' 2>/dev/null; then
        report_python="$candidate"; break
    fi
done
[[ -n "$report_python" ]] || { echo 'Python >= 3.9 is required.' >&2; exit 2; }
"$report_python" scripts/report_solver_needs_saved.py "${1:?Study directory}"
