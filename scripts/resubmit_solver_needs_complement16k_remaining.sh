#!/usr/bin/env bash
set -Eeuo pipefail
# Fresh preparation fingerprint, same original candidates and saved replay pool.
source_study="${1:-results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018}"
old_parent="${2:-results/solver-needs-qwen14b-remaining362-complement16k-single/seed-20261018}"
new_parent="${3:-results/solver-needs-qwen14b-remaining362-complement16k-single-rerun/seed-20261018}"
[[ -f "$source_study/manifest.json" ]] || { echo "Missing original 24k source: $source_study/manifest.json" >&2; exit 2; }
[[ -f "$old_parent/study/manifest.json" ]] || { echo "Missing prepared study: $old_parent/study/manifest.json" >&2; exit 2; }
pool="$old_parent/shared-initial-events"
[[ -d "$pool" ]] || { echo "Missing saved replay pool: $pool" >&2; exit 2; }
pool_count="$(find "$pool" -mindepth 2 -maxdepth 2 -name pool.json -type f | wc -l)"
if [[ "$pool_count" -ne 362 ]]; then
    echo "Expected 362 completed saved pool manifests; found $pool_count in $pool" >&2
    exit 2
fi
if [[ "$new_parent" == "$old_parent" ]]; then
    echo 'Choose a new output parent; do not overwrite the old prepared study.' >&2
    exit 2
fi
echo "New output: $new_parent/study"
echo "Reuse saved initial replays: $pool"
echo 'Keep the code/prompts unchanged until preparation, inference and comparison finish.'
mkdir -p logs
study="$new_parent/study"
prepare_id="$(sbatch --parsable scripts/slurm/solver_needs_prepare.slurm "$study" 362 \
    configs/solver-needs-tasks-remaining362.json configs/solver-needs-qwen14b-complement16k-single.json \
    "$source_study" "" "$pool")"
prepare_id="${prepare_id%%;*}"
run_id="$(sbatch --parsable --dependency="afterok:${prepare_id}" scripts/slurm/solver_needs_run.slurm "$study")"
run_id="${run_id%%;*}"
compare_id="$(sbatch --parsable --time=01:00:00 --dependency="afterany:${run_id}" scripts/slurm/solver_needs_compare.slurm "$study")"
echo "Preparation using saved evidence: $prepare_id"
echo "GPU inference (only base24k+complement16k): $run_id"
echo "Comparison (1 hour limit): ${compare_id%%;*}"
echo "Report: $study/comparison.md"
