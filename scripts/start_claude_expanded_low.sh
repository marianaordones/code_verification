#!/usr/bin/env bash
# Start this immediate local batch independently of the chat's terminal session.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
study=results/claude-local-expanded60-low-v2
if [[ "${1:-}" == worker ]]; then
    export PATH="$HOME/.local/bin:$PATH"
    echo "Waiting for preparation to release the study lock."
    flock "$study/.lock" true
    test -f "$study/manifest.json"
    echo "Preparation complete; starting the Low paired run."
    bash scripts/run_claude_expanded_low.sh run
    exit
fi
if [[ $# != 0 ]]; then
    echo "Usage: bash scripts/start_claude_expanded_low.sh" >&2
    exit 2
fi
test -f "$study/.lock"
pid_file=results/claude-expanded60-low.pid
if [[ -e "$pid_file" ]]; then
    echo "A batch PID file already exists; inspect it before starting another worker." >&2
    exit 2
fi
nohup bash scripts/start_claude_expanded_low.sh worker \
    > results/claude-expanded60-low-execution.log 2>&1 < /dev/null &
printf '%s\n' "$!" > "$pid_file"
echo "Batch started. PID: $(cat "$pid_file")"
echo "Log: results/claude-expanded60-low-execution.log"
