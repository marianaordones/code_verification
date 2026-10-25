#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export VB_CLAUDE_CONFIG=configs/verusbench-sonnet20-v2.json
# These are new original programs; do not import the previous five inputs.
unset VB_SOURCE_STUDY
bash scripts/run_verusbench_claude.sh "${1:?Use prepare, run or compare}" \
    "${2:-results/verusbench-sonnet20-low-v2}"
