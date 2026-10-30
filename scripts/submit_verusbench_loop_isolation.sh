#!/usr/bin/env bash
set -Eeuo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
source_study="${1:-results/verusbench-qwen14b-three-arms/seed-20261018}"
output="${2:-results/verusbench-loop-isolation-false/seed-20261018}"
[[ -f "$source_study/run.json" ]] || { echo "Missing source: $source_study/run.json" >&2; exit 2; }
mkdir -p logs
prepare="$(sbatch --parsable scripts/slurm/verusbench_loop_prepare.slurm "$source_study" "$output")"
prepare="${prepare%%;*}"
job50="$(sbatch --parsable --job-name=verus-loop-false-50 --dependency="afterok:$prepare" scripts/slurm/verusbench_loop_run.slurm "$output" batch50)"
job50="${job50%%;*}"
job55="$(sbatch --parsable --job-name=verus-loop-false-55 --dependency="afterok:$prepare" scripts/slurm/verusbench_loop_run.slurm "$output" batch55)"
job55="${job55%%;*}"
compare="$(sbatch --parsable --dependency="afterany:$job50:$job55" scripts/slurm/verusbench_loop_compare.slurm "$output")"
echo "Preparation CPU: $prepare"
echo "50 tasks, GPU job: $job50"
echo "55 tasks, GPU job: $job55"
echo "GPU jobs are independent; both depend only on preparation."
echo "Aggregation CPU: ${compare%%;*}"
echo "Report: $output/comparison.md"
