#!/usr/bin/env bash
# Same 100 initial candidates and saved replay events as the completed 24k run.
set -Eeuo pipefail
study="${1:-results/solver-needs-qwen14b-100-internals32k/seed-20261018}"
source_study="${2:-results/solver-needs-qwen14b-100-internals24k/seed-20261018}"
if [[ ! -f "$source_study/manifest.json" ]]; then
    echo "Missing completed 24k source manifest: $source_study/manifest.json" >&2
    exit 2
fi
bash scripts/submit_solver_needs.sh "$study" 100 \
    configs/solver-needs-tasks100.json configs/solver-needs-qwen14b-internals32k.json "$source_study"
