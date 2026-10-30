#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p logs
sbatch scripts/slurm/safe_full_coverage.slurm "$@"
echo 'Default report: analysis/safe-full-repair-coverage/coverage.md'
