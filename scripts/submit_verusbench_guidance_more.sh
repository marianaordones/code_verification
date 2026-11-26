#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
mkdir -p logs
sbatch scripts/slurm/verusbench_guidance_more.slurm "$@"
