#!/usr/bin/env bash
# Submit two independent paired repair studies; never regenerate the training export.
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

which="${1:-all}"
[[ $# == 0 ]] || shift
adapter="results/safe-multiedit-sft-v1/adapter"
sources="results/safe-sft-local-v1"
outputs="results/safe-multiedit-eval-v1"

usage() {
    cat <<'TXT'
Usage: bash scripts/submit_safe_multiedit_eval.sh all|verusbench|solver-needs [options]
  --adapter PATH       Completed multi-edit adapter directory
  --source-root PATH   Root containing prior verusbench/ and solver-needs/ studies
  --output-root PATH   New evaluation root (same path when resuming)

Defaults: results/safe-multiedit-sft-v1/adapter,
          results/safe-sft-local-v1, results/safe-multiedit-eval-v1.
EVAL_GPU_TYPE=L40S and EVAL_TIME=2-00:00:00 can override GPU type and wall time.
Each dataset gets one high_performance/high job, with both feedback arms.
Repair-only: three JSON multi-edit proposals per eligible frozen failed candidate.
No old successful first proposals are credited to this adapter. No inference runs here.
TXT
}

case "$which" in
    all|verusbench|solver-needs) ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac
while [[ $# -gt 0 ]]; do
    case "$1" in
        --adapter) adapter="${2:?adapter directory required}"; shift 2 ;;
        --source-root) sources="${2:?source root required}"; shift 2 ;;
        --output-root) outputs="${2:?output root required}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# Complete preflight for both datasets before submitting the first job.
command -v sbatch >/dev/null || { echo 'sbatch is unavailable; run on the cluster login node.' >&2; exit 2; }
for name in adapter_config.json adapter_model.safetensors; do
    [[ -s "$adapter/$name" ]] || { echo "Missing trained adapter file: $adapter/$name" >&2; exit 2; }
done
[[ -s "$adapter/../training-provenance.json" ]] || {
    echo "Missing training provenance beside adapter: $adapter/../training-provenance.json" >&2; exit 2;
}
for benchmark in verusbench solver-needs; do
    [[ "$which" == all || "$which" == "$benchmark" ]] || continue
    [[ -s "$sources/$benchmark/manifest.json" && -d "$sources/$benchmark/inputs" ]] || {
        echo "Missing frozen study: $sources/$benchmark. Set --source-root to its actual parent directory." >&2; exit 2;
    }
done
adapter="$(cd "$adapter" && pwd -P)"
sources="$(cd "$sources" && pwd -P)"
mkdir -p logs "$outputs"
outputs="$(cd "$outputs" && pwd -P)"
[[ "$outputs" != "$sources" && "$outputs" != "$sources/"* && "$sources" != "$outputs/"* ]] || {
    echo 'Output and source must be separate study trees.' >&2; exit 2;
}
receipt="logs/safe-multiedit-eval-submission-$(date +%Y%m%dT%H%M%S)-$$.tsv"
printf 'benchmark\tjob_id\tadapter\tsource\toutput\n' > "$receipt"
echo "Submission record: $receipt"
echo 'Protocol: frozen failures; 3 multi-edit repair proposals; with/without base24k (50x3).'
for benchmark in verusbench solver-needs; do
    [[ "$which" == all || "$which" == "$benchmark" ]] || continue
    job="$(sbatch --parsable --partition=high_performance --qos=high \
        --gres="gpu:${EVAL_GPU_TYPE:-L40S}:1" --time="${EVAL_TIME:-2-00:00:00}" \
        --job-name="safe-multi-$benchmark" scripts/slurm/safe_multiedit_eval.slurm "$benchmark" \
        --source "$sources/$benchmark" --adapter "$adapter" --output "$outputs/$benchmark")"
    job="${job%%;*}"
    printf '%s\t%s\t%s\t%s\t%s\n' "$benchmark" "$job" "$adapter" "$sources/$benchmark" "$outputs/$benchmark" >> "$receipt"
    echo "$benchmark: job=$job; output=$outputs/$benchmark"
done
