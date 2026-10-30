#!/usr/bin/env bash
set -Eeuo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$project_root"
dataset="${1:-data/safe/sft_safe_25k.json}"
parent="${2:-results/safe-internals-remaining-attrs-v2}"
# Argument 3 optionally resumes one batch instead of submitting all four.
batch_filter="${3:-all}"
# Kit dated 2026-10-14 plus viper07's observed startup failures. Not a health probe.
avoid_nodes="${SAFE_EXCLUDE_NODES-viper01,viper02,viper03,viper05,viper06,viper07,viper08}"
case "$batch_filter" in all|a|b|c|d) ;; *) echo 'Argument 3 must be all, a, b, c or d' >&2; exit 2 ;; esac
[[ -f "$dataset" ]] || { echo "Missing SAFE JSON: $dataset" >&2; exit 2; }
mkdir -p logs
required=(scripts/slurm/safe_internals_remaining.slurm scripts/prepare_safe_internals_remaining.py
          scripts/cluster/setup_safe_cpu.sh scripts/cluster/setup_safe_rust.sh
          scripts/cluster/stage_tools.sh scripts/cluster/setup_z3_internals.sh
          tests/test_safe_remaining.py)
for batch in a b c d; do
    required+=("configs/safe-internals-remaining-$batch.json" "configs/safe-repair-remaining-$batch.json")
done
for file in "${required[@]}"; do
    [[ -s "$file" ]] || { echo "Missing/empty required file: $file" >&2; exit 2; }
done
if LC_ALL=C grep -q $'\r' scripts/slurm/safe_internals_remaining.slurm; then
    echo 'The Slurm script has Windows CRLF endings; transfer it with Linux LF endings.' >&2
    exit 2
fi
bash -n scripts/slurm/safe_internals_remaining.slurm
dataset="$(realpath -- "$dataset")"
mkdir -p "$parent"
parent="$(cd -- "$parent" && pwd -P)"
receipt="$project_root/logs/safe-remaining-submission-$(date +%Y%m%dT%H%M%S)-$$.tsv"
printf 'job_id\tbatch\tstdout\tstderr\toutput\texcluded_nodes\n' > "$receipt"
echo "Submission record: $receipt"
for batch in a b c d; do
    [[ "$batch_filter" == all || "$batch_filter" == "$batch" ]] || continue
    output="$parent/$batch/seed-20261018"
    job="$(sbatch --parsable --hold --partition=new_p_general --qos=high --chdir="$project_root" --job-name="safe-internals-rest-$batch" \
        --output="$project_root/logs/%x-%j.out" --error="$project_root/logs/%x-%j.err" \
        "$project_root/scripts/slurm/safe_internals_remaining.slurm" \
        "$batch" "$dataset" "$output")"
    job="${job%%;*}"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$job" "$batch" \
        "$project_root/logs/safe-internals-rest-$batch-$job.out" \
        "$project_root/logs/safe-internals-rest-$batch-$job.err" "$output" "$avoid_nodes" >> "$receipt"
    echo "Created held job: $job (batch $batch)"
    if [[ -n "$avoid_nodes" ]]; then
        if ! scontrol update "jobid=$job" "ExcNodeList=$avoid_nodes"; then
            echo "Could not exclude nodes; job $job remains HELD and was not released." >&2
            echo "Inspect with: scontrol show job $job" >&2
            exit 2
        fi
    fi
    if ! scontrol release "$job"; then
        echo "Could not release job $job; inspect its state before resubmitting." >&2
        exit 2
    fi
    echo "Batch $batch (2942 repair rows), independent CPU job: ${job%%;*}"
    echo "Report: $output/report.md"
    echo "stdout: $project_root/logs/safe-internals-rest-$batch-$job.out"
    echo "stderr: $project_root/logs/safe-internals-rest-$batch-$job.err"
done
echo 'Four new shards cover the 11768 remaining repair rows; the first 2000 are excluded.'
echo 'No GPU is requested. Keep shared collector code unchanged while jobs run.'
echo "Partition: new_p_general; QoS: high; excluded nodes: ${avoid_nodes:-none}."
