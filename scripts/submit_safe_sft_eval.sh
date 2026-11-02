#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
which="${1:-all}"
adapter="${2:-results/safe-sft-a100-v1/adapter}"
parent="${3:-results/safe-sft-eval-v1}"
case "$which" in all|verusbench|solver-needs) ;; *) echo 'Use all, verusbench or solver-needs' >&2; exit 2 ;; esac
[[ -s "$adapter/adapter_model.safetensors" ]] || { echo "Missing trained adapter: $adapter" >&2; exit 2; }
mkdir -p logs "$parent"
adapter="$(cd "$adapter" && pwd -P)"
parent="$(cd "$parent" && pwd -P)"
receipt="logs/safe-sft-eval-submission-$(date +%Y%m%dT%H%M%S)-$$.tsv"
printf 'benchmark\tprepare\trun\treport\toutput\n' > "$receipt"
avoid="${SAFE_EXCLUDE_NODES-viper01,viper02,viper03,viper05,viper06,viper07,viper08}"
gpu_options=(--gres="gpu:${SFT_GPU_TYPE:+${SFT_GPU_TYPE}:}1")
[[ -z "${SFT_PARTITION:-}" ]] || gpu_options+=(--partition="$SFT_PARTITION")
release_cpu() {
    local job="${1%%;*}"
    if [[ -n "$avoid" ]]; then
        scontrol update "JobId=$job" "ExcNodeList=$avoid" || { echo "Job $job remains held: exclusions failed" >&2; return 1; }
    fi
    scontrol release "$job"
}
for benchmark in verusbench solver-needs; do
    [[ "$which" == all || "$which" == "$benchmark" ]] || continue
    output="$parent/$benchmark"
    prep="$(sbatch --parsable --hold --job-name="safe-eval-prep-$benchmark" scripts/slurm/safe_sft_eval_prepare.slurm \
        "$benchmark" --adapter "$adapter" --output "$output")"
    prep="${prep%%;*}"
    release_cpu "$prep"
    run="$(sbatch --parsable "${gpu_options[@]}" --dependency="afterok:$prep" --job-name="safe-eval-$benchmark" \
        scripts/slurm/safe_sft_eval_run.slurm "$benchmark" --output "$output")"
    run="${run%%;*}"
    summary="$(sbatch --parsable --hold --dependency="afterany:$run" scripts/slurm/safe_sft_eval_report.slurm --output "$output")"
    summary="${summary%%;*}"
    release_cpu "$summary"
    printf '%s\t%s\t%s\t%s\t%s\n' "$benchmark" "$prep" "$run" "$summary" "$output" >> "$receipt"
    echo "$benchmark: prepare=$prep run=$run report=$summary output=$output"
done
echo "Submission record: $receipt"
