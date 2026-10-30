#!/usr/bin/env bash
# Login-node diagnostics only: no submission, cancellation, install, or solver.
set -uo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$project_root"
job_ids="${1:-13293,13294,13295,13296}"
if [[ ! "$job_ids" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
    echo 'Pass comma-separated numeric job IDs.' >&2; exit 2
fi
mkdir -p logs
report="$project_root/logs/safe-remaining-diagnosis-${job_ids//,/-}.txt"
{
    echo "SAFE remaining diagnostic; project=$project_root; jobs=$job_ids"
    echo '--- Slurm accounting, including batch-step failures ---'
    sacct -j "$job_ids" --format=JobID,JobName%28,State,ExitCode,Elapsed,NodeList || true
    IFS=, read -r -a ids <<< "$job_ids"
    for id in "${ids[@]}"; do
        echo "--- Scheduler details for job $id (may expire after completion) ---"
        scontrol show job "$id" || true
        for extension in out err; do
            matched=false
            for path in "$project_root"/logs/*-"$id"."$extension"; do
                [[ -f "$path" ]] || continue
                matched=true
                echo "--- $path ($(wc -c < "$path") bytes), last 80 lines ---"
                tail -n 80 "$path"
            done
            "$matched" || echo "No .$extension file found for job $id in $project_root/logs"
        done
    done
    echo '--- Slurm script format ---'
    if [[ -f scripts/slurm/safe_internals_remaining.slurm ]]; then
        wc -l -c scripts/slurm/safe_internals_remaining.slurm
        bash -n scripts/slurm/safe_internals_remaining.slurm || true
        if LC_ALL=C grep -q $'\r' scripts/slurm/safe_internals_remaining.slurm; then
            echo 'CRLF detected in Slurm script'
        else
            echo 'LF endings (no CR detected)'
        fi
    else
        echo 'Slurm script missing'
    fi
} 2>&1 | tee "$report"
echo "Diagnostic report: $report"
