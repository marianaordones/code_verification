#!/usr/bin/env bash
set -Eeuo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
source_study="${1:-results/solver-needs-qwen14b-100-internals24k/seed-20261018}"
parent="${2:-results/solver-needs-qwen14b-100-advanced64k/seed-20261018}"
if [[ ! -f "$source_study/manifest.json" ]]; then
    echo "Missing completed original 24k/50x3 source: $source_study/manifest.json" >&2
    exit 1
fi
bash scripts/submit_solver_needs.sh "$parent/study" 100 \
    configs/solver-needs-tasks100.json configs/solver-needs-qwen14b-advanced64k.json \
    "$source_study" "" "$parent/shared-initial-events"
