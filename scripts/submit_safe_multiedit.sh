#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
mode="${1:?Use convert, smoke, train, eval-verusbench, eval-solver-needs or report}"
shift
mkdir -p logs
case "$mode" in
  convert)
    sbatch scripts/slurm/safe_multiedit_convert.slurm "$@"
    ;;
  smoke|train)
    extra=()
    [[ "$mode" != smoke ]] || extra+=(--smoke)
    wall="${SFT_TIME:-3-00:00:00}"
    [[ "$mode" != smoke ]] || wall=04:00:00
    sbatch --partition=high_performance --qos=high --gres="gpu:${SFT_GPU_TYPE:-A100}:1" \
      --time="$wall" scripts/slurm/safe_multiedit_train.slurm "${extra[@]}" "$@"
    ;;
  eval-verusbench|eval-solver-needs)
    sbatch --partition=high_performance --qos=high --gres="gpu:${EVAL_GPU_TYPE:-L40S}:1" \
      scripts/slurm/safe_multiedit_eval.slurm "${mode#eval-}" "$@"
    ;;
  report)
    sbatch scripts/slurm/safe_multiedit_convert.slurm --report "$@"
    ;;
  *) echo 'Unknown mode' >&2; exit 2 ;;
esac
