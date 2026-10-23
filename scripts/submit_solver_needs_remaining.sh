#!/usr/bin/env bash
# Remaining paper Verus/Z3 tasks: exact complement of the frozen first 100 IDs.
set -Eeuo pipefail
study="${1:-results/solver-needs-qwen14b-remaining362/seed-20261018}"
bash scripts/submit_solver_needs.sh "$study" 362 configs/solver-needs-tasks-remaining362.json
