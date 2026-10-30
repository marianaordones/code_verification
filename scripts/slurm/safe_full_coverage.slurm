#!/usr/bin/env bash
#SBATCH --job-name=safe-full-coverage
#SBATCH --partition=high_performance
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from repository root}"
if [[ -f cluster.env ]]; then source ./cluster.env; fi
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
coverage_python=""
for candidate in "${CLUSTER_PYTHON:-}" python3.12 python3.11 python3; do
    [[ -n "$candidate" ]] || continue
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; assert sys.version_info >= (3,9)' 2>/dev/null; then
        coverage_python="$candidate"; break
    fi
done
[[ -n "$coverage_python" ]] || { echo 'Python >= 3.9 required' >&2; exit 2; }
"$coverage_python" scripts/report_safe_full_coverage.py "$@"
