#!/usr/bin/env bash
# Exact original 24k/50x3 settings; only the fixed task list changes to its complement.
set -Eeuo pipefail
study="${1:-results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018}"
reference="${2:-results/solver-needs-qwen14b-100-internals24k/seed-20261018}"
if [[ ! -f "$reference/manifest.json" ]]; then
    echo "Missing original 24k settings reference: $reference/manifest.json" >&2
    exit 2
fi
bash scripts/submit_solver_needs.sh "$study" 362 \
    configs/solver-needs-tasks-remaining362.json \
    configs/solver-needs-qwen14b-internals24k.json "" "$reference"
