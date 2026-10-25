#!/usr/bin/env bash
set -Eeuo pipefail
# Run from repository root. Source is the completed original 24k / 50x3 study.
source_study="${1:-results/solver-needs-qwen14b-100-internals24k/seed-20261018}"
parent="${2:-results/solver-needs-qwen14b-100-complement16k/seed-20261018}"
if [[ ! -f "$source_study/manifest.json" ]]; then
    echo "Missing source manifest: $source_study/manifest.json" >&2
    exit 1
fi
bash scripts/submit_solver_needs.sh "$parent/study" 100 \
    configs/solver-needs-tasks100.json configs/solver-needs-qwen14b-complement16k.json \
    "$source_study" "" "$parent/shared-initial-events"
