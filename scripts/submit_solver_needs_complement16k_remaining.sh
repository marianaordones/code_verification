#!/usr/bin/env bash
set -Eeuo pipefail
# Only base24k+16k, on the frozen remaining 362 IDs. No control inference.
source_study="${1:-results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018}"
parent="${2:-results/solver-needs-qwen14b-remaining362-complement16k-single/seed-20261018}"
if [[ ! -f "$source_study/manifest.json" ]]; then
    echo "Missing completed remaining-362 24k/50x3 source: $source_study/manifest.json" >&2
    echo "Pass its study directory as the first argument (absolute paths are supported)." >&2
    exit 1
fi
bash scripts/submit_solver_needs.sh "$parent/study" 362 \
    configs/solver-needs-tasks-remaining362.json configs/solver-needs-qwen14b-complement16k-single.json \
    "$source_study" "" "$parent/shared-initial-events"
