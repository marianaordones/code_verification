#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
which="${1:-all}"
sources="${2:-results/safe-sft-eval-v1}"
outputs="${3:-results/safe-sft-local-v1}"
case "$which" in all|verusbench|solver-needs) ;; *) echo 'Use all, verusbench or solver-needs' >&2; exit 2 ;; esac
mkdir -p logs "$outputs"
sources="$(cd "$sources" && pwd -P)"
outputs="$(cd "$outputs" && pwd -P)"
avoid="${SAFE_EXCLUDE_NODES-viper01,viper02,viper03,viper05,viper06,viper07,viper08}"
gpu_options=(--gres="gpu:${SFT_GPU_TYPE:+${SFT_GPU_TYPE}:}1")
[[ -z "${SFT_PARTITION:-}" ]] || gpu_options+=(--partition="$SFT_PARTITION")
release_cpu() {
    local id="${1%%;*}"
    if [[ -n "$avoid" ]]; then
        scontrol update "JobId=$id" "ExcNodeList=$avoid" || { echo "Job $id remains held" >&2; return 1; }
    fi
    scontrol release "$id"
}
for benchmark in verusbench solver-needs; do
    [[ "$which" == all || "$which" == "$benchmark" ]] || continue
    [[ -s "$sources/$benchmark/manifest.json" ]] || { echo "Missing full-file source manifest: $sources/$benchmark" >&2; exit 2; }
done
receipt="logs/safe-local-submission-$(date +%Y%m%dT%H%M%S)-$$.tsv"
printf 'benchmark\tprepare\trun\treport\toutput\n' > "$receipt"
for benchmark in verusbench solver-needs; do
    [[ "$which" == all || "$which" == "$benchmark" ]] || continue
    prep="$(sbatch --parsable --hold --job-name="safe-local-prep-$benchmark" scripts/slurm/safe_sft_local_prepare.slurm \
        "$benchmark" --source "$sources/$benchmark" --output "$outputs/$benchmark")"
    prep="${prep%%;*}"
    release_cpu "$prep"
    run="$(sbatch --parsable "${gpu_options[@]}" --dependency="afterok:$prep" --job-name="safe-local-$benchmark" \
        scripts/slurm/safe_sft_local_run.slurm "$benchmark" --output "$outputs/$benchmark")"
    run="${run%%;*}"
    summary="$(sbatch --parsable --hold --dependency="afterany:$run" scripts/slurm/safe_sft_local_report.slurm --output "$outputs/$benchmark")"
    summary="${summary%%;*}"
    release_cpu "$summary"
    printf '%s\t%s\t%s\t%s\t%s\n' "$benchmark" "$prep" "$run" "$summary" "$outputs/$benchmark" >> "$receipt"
    echo "$benchmark: prepare=$prep run=$run report=$summary"
done
echo "Submission record: $receipt"
