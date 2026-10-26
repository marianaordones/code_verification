#!/usr/bin/env bash
set -Eeuo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
mkdir -p logs
job_id="$(sbatch --parsable --chdir="$project_root" scripts/slurm/z3_advanced_pilot.slurm "$@")"
job_id="${job_id%%;*}"
echo "CPU-only Z3 advanced pilot: $job_id"
echo "Logs: logs/z3-advanced-pilot-${job_id}.out and .err"
echo "Default report: results/z3-advanced-pilot/job-${job_id}/report.md"
