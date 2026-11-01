#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
mode="${1:?Use validate-generation, prepare, smoke or train}"
shift
mkdir -p logs
case "$mode" in
  validate-generation|prepare)
    file=scripts/slurm/safe_sft_prepare.slurm
    [[ "$mode" != validate-generation ]] || file=scripts/slurm/safe_generation_validate.slurm
    job="$(sbatch --parsable --hold "$file" "$@")"
    job="${job%%;*}"
    echo "Held job: $job"
    avoid="${SAFE_EXCLUDE_NODES-viper01,viper02,viper03,viper05,viper06,viper07,viper08}"
    if [[ -n "$avoid" ]]; then
      scontrol update "JobId=$job" "ExcNodeList=$avoid" || { echo "Job $job remains held; node exclusion failed" >&2; exit 1; }
    fi
    scontrol release "$job"
    echo "Released job: $job"
    ;;
  smoke|train)
    gpu_options=(--gres="gpu:${SFT_GPU_TYPE:+${SFT_GPU_TYPE}:}1")
    [[ -z "${SFT_PARTITION:-}" ]] || gpu_options+=(--partition="$SFT_PARTITION")
    [[ -z "${SFT_NODE:-}" ]] || gpu_options+=(--nodelist="$SFT_NODE")
    if [[ "$mode" == smoke ]]; then
      sbatch "${gpu_options[@]}" --time=04:00:00 scripts/slurm/safe_sft_train.slurm --smoke "$@"
    else
      sbatch "${gpu_options[@]}" scripts/slurm/safe_sft_train.slurm "$@"
    fi
    ;;
  *) echo 'Use validate-generation, prepare, smoke or train' >&2; exit 2 ;;
esac
