#!/usr/bin/env bash
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
stage="${1:?Use: run_experiment.sh prepare|pilot|pilot14|pilot14-50|coder14-100|coder14-150|coder14-150-v4|coder14-150-b|coder14-150-b-96k|revalidate|baseline}"
shift

if [[ "$stage" == prepare ]]; then
    bash scripts/cluster/setup_tools.sh
fi
source scripts/cluster/stage_tools.sh
export VERUS_Z3_PATH="${Z3_BIN:?Missing Z3 path}"
: "${VERUS_BIN:?Missing Verus path}"
: "${LYNETTE_BIN:?Missing Lynette path}"

seed=20261018
base="results/seed-${seed}"
if [[ "$stage" == pilot14 ]]; then
    base="results/qwen14b-v2-10/seed-${seed}"
elif [[ "$stage" == pilot14-50 ]]; then
    base="results/qwen14b-v2-50/seed-${seed}"
elif [[ "$stage" == coder14-100 ]]; then
    base="results/qwen25coder14b-v2-100/seed-${seed}"
elif [[ "$stage" == coder14-150 ]]; then
    base="results/qwen25coder14b-v3-150/seed-${seed}"
elif [[ "$stage" == coder14-150-v4 ]]; then
    base="results/qwen25coder14b-v4-150/seed-${seed}"
elif [[ "$stage" == coder14-150-b ]]; then
    base="results/qwen25coder14b-b-150/seed-${seed}"
elif [[ "$stage" == coder14-150-b-96k ]]; then
    base="results/qwen25coder14b-b-96k-150/seed-${seed}"
elif [[ "$stage" == coder14-150-c-internals ]]; then
    base="results/qwen25coder14b-c-internals-150/seed-${seed}"
elif [[ "$stage" == revalidate ]]; then
    base="${2:?Pass source and output directories}"
fi
mkdir -p "$base"
monitor_pid=""
# Map telemetry to the allocated logical device; never monitor every physical GPU
# and attribute all of them to this job.
gpu_uuid="$(python -c 'import torch; print(getattr(torch.cuda.get_device_properties(0), "uuid", ""))')"
if [[ "$gpu_uuid" == GPU-* ]]; then
    nvidia-smi -i "$gpu_uuid" --query-gpu=timestamp,uuid,utilization.gpu,memory.used,power.draw \
        --format=csv -l 1 > "${base}/gpu-${SLURM_JOB_ID:-local}.csv" &
    monitor_pid=$!
    trap 'kill "$monitor_pid" 2>/dev/null || true' EXIT
else
    echo "GPU UUID unavailable; skipping optional GPU samples to avoid mixing devices."
fi

case "$stage" in
    prepare)
        # Both variables are set: the real tool test must execute, never skip.
        python -m unittest discover -s tests -v
        python -c 'from baseline.inference import prepare_model; print(prepare_model())'
        for mode in nonthinking thinking; do
            python -m baseline run --stage smoke --config "configs/${mode}.json" \
                --task cloverbench_array_copy_strong --task cloverbench_array_sum_strong \
                --output "${base}/smoke/${mode}"
        done
        echo "PREPARATION AND REAL SMOKE TESTS COMPLETE"
        echo "Next: sbatch scripts/slurm/pilot.slurm"
        ;;
    pilot|pilot14|pilot14-50)
        # Fail early on incompatible tools before any expensive generation.
        python -m unittest discover -s tests -p test_tools.py -v
        for mode in thinking nonthinking; do
            config="configs/${mode}.json"
            if [[ "$stage" == pilot14 ]]; then config="configs/qwen14b-v2-${mode}.json"; fi
            if [[ "$stage" == pilot14-50 ]]; then config="configs/qwen14b-v2-50-${mode}.json"; fi
            python -m baseline run --stage pilot --config "$config" \
                --output "${base}/pilot/${mode}"
        done
        python -m baseline report --thinking "${base}/pilot/thinking" \
            --nonthinking "${base}/pilot/nonthinking" --output "${base}/pilot/report"
        echo "PILOT COMPLETE. Read ${base}/pilot/report.md before choosing a mode."
        ;;
    coder14-100)
        python -m unittest discover -s tests -p test_tools.py -v
        python -m baseline run --stage pilot --config configs/qwen25coder14b-v2-100.json \
            --output "${base}/pilot/instruct"
        python -m baseline single-report "${base}/pilot/instruct"
        echo "EXPERIMENT COMPLETE. Read ${base}/pilot/instruct/report.md"
        ;;
    coder14-150)
        python -m unittest discover -s tests -p test_tools.py -v
        python -m baseline run --stage full --config configs/qwen25coder14b-v3-150.json \
            --output "${base}/full/instruct"
        python -m baseline single-report "${base}/full/instruct"
        echo "EXPERIMENT COMPLETE. Read ${base}/full/instruct/report.md"
        ;;
    coder14-150-v4)
        python -m unittest discover -s tests -p test_tools.py -v
        python -m baseline run --stage full --config configs/qwen25coder14b-v4-150.json \
            --output "${base}/full/instruct"
        python -m baseline single-report "${base}/full/instruct"
        echo "EXPERIMENT COMPLETE. Read ${base}/full/instruct/report.md"
        ;;
    coder14-150-b)
        python -m unittest discover -s tests -p test_tools.py -v
        python -m unittest discover -s tests -p test_obligation.py -v
        python -m baseline run --stage full --config configs/qwen25coder14b-b-150.json \
            --output "${base}/full/instruct"
        python -m baseline single-report "${base}/full/instruct"
        echo "EXPERIMENT B COMPLETE. Read ${base}/full/instruct/report.md"
        ;;
    coder14-150-b-96k)
        python -m unittest discover -s tests -p test_tools.py -v
        python -m unittest discover -s tests -p test_obligation.py -v
        python -m unittest discover -s tests -p test_b96k.py -v
        python -m baseline run --stage full --config configs/qwen25coder14b-b-96k-150.json \
            --output "${base}/full/instruct"
        python -m baseline single-report "${base}/full/instruct"
        echo "EXPERIMENT B/96k COMPLETE. Read ${base}/full/instruct/report.md"
        ;;
    coder14-150-c-internals)
        source scripts/cluster/setup_z3_internals.sh
        python -m unittest discover -s tests -p test_tools.py -v
        python -m unittest discover -s tests -p test_obligation.py -v
        python -m unittest discover -s tests -p test_internals.py -v
        python -m baseline run --stage full --config configs/qwen25coder14b-c-internals-150.json \
            --output "${base}/full/instruct"
        python -m baseline single-report "${base}/full/instruct"
        echo "EXPERIMENT C COMPLETE. Read ${base}/full/instruct/report.md"
        ;;
    revalidate)
        python -m unittest discover -s tests -p test_tools.py -v
        python -m baseline revalidate --source "${1:?Source run directory}" --output "${2:?Output directory}"
        ;;
    baseline)
        config="${1:?Pass configs/thinking.json or configs/nonthinking.json}"
        decision="${2:?Pass decision.json after reviewing the pilot}"
        mode="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["mode"])' "$config")"
        [[ "$mode" == thinking || "$mode" == nonthinking ]] || exit 35
        python -m baseline run --stage baseline --config "$config" --decision "$decision" \
            --output "${base}/baseline/${mode}"
        ;;
    *) echo "Unknown stage: $stage" >&2; exit 2 ;;
esac
