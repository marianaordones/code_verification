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
  smoke) sbatch --time=04:00:00 scripts/slurm/safe_sft_train.slurm --smoke "$@" ;;
  train) sbatch scripts/slurm/safe_sft_train.slurm "$@" ;;
  *) echo 'Use validate-generation, prepare, smoke or train' >&2; exit 2 ;;
esac
