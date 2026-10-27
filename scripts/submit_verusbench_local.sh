#!/usr/bin/env bash
set -Eeuo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
source_study="${1:-results/verusbench-qwen14b-three-arms/seed-20261018}"
output="${2:-results/verusbench-local-base24k/seed-20261018}"
[[ -f "$source_study/run.json" ]] || { echo "Missing source run: $source_study/run.json" >&2; exit 2; }
mkdir -p logs
prep="$(sbatch --parsable scripts/slurm/verusbench_local_prepare.slurm "$source_study" "$output")"
prep="${prep%%;*}"
run="$(sbatch --parsable --dependency="afterok:$prep" scripts/slurm/verusbench_local_run.slurm "$output")"
run="${run%%;*}"
echo "Preparation: $prep"
echo "Both localized arms on one GPU: $run"
echo "Report: $output/comparison.md"
