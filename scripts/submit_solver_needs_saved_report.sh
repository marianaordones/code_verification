#!/usr/bin/env bash
set -Eeuo pipefail
study="${1:-results/solver-needs-qwen14b-remaining362-complement16k-single/seed-20261018/study}"
[[ -f "$study/manifest.json" ]] || { echo "Missing manifest: $study/manifest.json" >&2; exit 2; }
mkdir -p logs
sbatch scripts/slurm/solver_needs_saved_report.slurm "$study"
echo "Report: $study/saved-report/comparison.md"
