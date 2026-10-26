#!/usr/bin/env bash
set -Eeuo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
mkdir -p logs
job_id="$(sbatch --parsable --chdir="$project_root" scripts/slurm/solver_needs_three_proposals.slurm "$@")"
job_id="${job_id%%;*}"
echo "Three-proposal analysis submitted: $job_id"
echo "Output log: logs/solver-needs-three-${job_id}.out"
echo "Error log: logs/solver-needs-three-${job_id}.err"
echo "Default reports: analysis/solver-needs-full-three-proposals/"
