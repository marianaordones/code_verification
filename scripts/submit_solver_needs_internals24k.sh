#!/usr/bin/env bash
# Same frozen first 100 IDs, larger internal-feedback sample, same 48k context.
set -Eeuo pipefail
study="${1:-results/solver-needs-qwen14b-100-internals24k/seed-20261018}"
bash scripts/submit_solver_needs.sh "$study" 100 \
    configs/solver-needs-tasks100.json configs/solver-needs-qwen14b-internals24k.json
