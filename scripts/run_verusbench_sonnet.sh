#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export VB_CLAUDE_CONFIG=configs/verusbench-sonnet5.json
export VB_SOURCE_STUDY="${VB_SOURCE_STUDY:-results/verusbench-claude5-low-v2}"
bash scripts/run_verusbench_claude.sh "${1:?Use prepare, run or compare}" \
    "${2:-results/verusbench-sonnet5-low-v1}"
