#!/usr/bin/env bash
set -Eeuo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
mkdir -p logs
output="${1:-results/verusbench-qwen14b-three-arms/seed-20261018}"
job_id="$(sbatch --parsable scripts/slurm/verusbench_three_arms.slurm "$output")"
echo "VerusBench three arms: ${job_id%%;*}"
echo "Report: $output/comparison.md"
