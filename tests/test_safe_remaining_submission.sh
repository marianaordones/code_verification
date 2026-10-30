#!/usr/bin/env bash
# Simulated Slurm only. No jobs, model, solver or downloads.
set -Eeuo pipefail
repo="$(pwd)"
work="$(mktemp -d)"
trap '[[ -d "$work" && "${work##*/}" = tmp.* ]] && rm -rf -- "$work"' EXIT
project="$work/project"
mkdir -p "$project/scripts/slurm" "$project/scripts/cluster" "$project/configs" "$project/tests" "$project/data/safe" "$work/bin"
cp scripts/submit_safe_internals_remaining.sh "$project/scripts/"
cp scripts/slurm/safe_internals_remaining.slurm "$project/scripts/slurm/"
for file in scripts/prepare_safe_internals_remaining.py tests/test_safe_remaining.py \
            scripts/cluster/setup_safe_cpu.sh scripts/cluster/setup_safe_rust.sh \
            scripts/cluster/stage_tools.sh scripts/cluster/setup_z3_internals.sh; do
    printf 'mock\n' > "$project/$file"
done
for batch in a b c d; do
    printf '{}\n' > "$project/configs/safe-internals-remaining-$batch.json"
    printf '{}\n' > "$project/configs/safe-repair-remaining-$batch.json"
done
printf '[]\n' > "$project/data/safe/sft_safe_25k.json"
export MOCK_SAFE_CALLS="$work/calls"
cat > "$work/bin/sbatch" <<'SH'
#!/usr/bin/env bash
printf 'sbatch %s\n' "$*" >> "$MOCK_SAFE_CALLS"
[[ " $* " == *' --hold '* ]]
[[ " $* " == *' --partition=new_p_general '* ]]
[[ " $* " == *' --qos=high '* ]]
[[ " $* " != *' --exclude='* && " $* " != *' --nodelist='* && " $* " != *' --gres='* ]]
echo 900001
SH
cat > "$work/bin/scontrol" <<'SH'
#!/usr/bin/env bash
printf 'scontrol %s\n' "$*" >> "$MOCK_SAFE_CALLS"
if [[ "$1" == update && "${MOCK_SAFE_FAIL_UPDATE:-0}" == 1 ]]; then exit 7; fi
SH
chmod +x "$work/bin/sbatch" "$work/bin/scontrol"
export PATH="$work/bin:$PATH"
bash "$project/scripts/submit_safe_internals_remaining.sh" "$project/data/safe/sft_safe_25k.json" "$work/output" a > "$work/success"
grep -q '^scontrol update jobid=900001 ExcNodeList=' "$MOCK_SAFE_CALLS"
grep -q '^scontrol release 900001' "$MOCK_SAFE_CALLS"
[[ "$(wc -l < "$MOCK_SAFE_CALLS")" -eq 3 ]]
: > "$MOCK_SAFE_CALLS"
if MOCK_SAFE_FAIL_UPDATE=1 bash "$project/scripts/submit_safe_internals_remaining.sh" "$project/data/safe/sft_safe_25k.json" "$work/output" a > "$work/failure" 2>&1; then
    echo 'Expected failed exclusion update to stop submission' >&2; exit 1
else
    [[ "$?" == 2 ]]
fi
! grep -q '^scontrol release' "$MOCK_SAFE_CALLS"
grep -q 'remains HELD' "$work/failure"
echo 'Mock Slurm submission: correct partition/QoS, held-update-release order, failure remains held: OK'
