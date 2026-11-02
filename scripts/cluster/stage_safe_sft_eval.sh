#!/usr/bin/env bash
# Preserve all registered scratch directories when the existing staging helpers
# re-source native_workspace.sh. Cleanup must include the CPU runtime and both bundles.
declare -a NATIVE_WORKSPACES
eval_native_before=("${NATIVE_WORKSPACES[@]}")
source scripts/cluster/stage_tools.sh
NATIVE_WORKSPACES=("${eval_native_before[@]}" "${NATIVE_WORKSPACES[@]}")
if [[ "$benchmark" == solver-needs ]]; then
    eval_native_before=("${NATIVE_WORKSPACES[@]}")
    source scripts/cluster/stage_solver_needs.sh
    NATIVE_WORKSPACES=("${eval_native_before[@]}" "${NATIVE_WORKSPACES[@]}")
fi
