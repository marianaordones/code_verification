#!/usr/bin/env bash
# Sourced helper: executable files must live on a working local filesystem.
native_workspace() {
    local required_gb="${1:?Required free GB}" parent free_gb work filesystem
    for parent in "${CLUSTER_BUILD_TMP:-}" "${SLURM_TMPDIR:-}" /tmp /var/tmp; do
        [[ -n "$parent" && -d "$parent" && -w "$parent" && "$parent" != /dev/shm* ]] || continue
        filesystem="$(stat -f -c %T "$parent" 2>/dev/null || echo unknown)"
        case "$filesystem" in
            cifs|smb2|nfs|nfs4|fuse.sshfs)
                echo "Skipping network filesystem $parent ($filesystem) for native Rust execution." >&2
                continue ;;
        esac
        free_gb="$(df -Pk "$parent" 2>/dev/null | awk 'NR==2 {print int($4/1048576)}')" || continue
        [[ "${free_gb:-0}" -ge "$required_gb" ]] || continue
        work="$(mktemp -d "${parent%/}/verus-native-${SLURM_JOB_ID:-local}-XXXXXXXX")" || continue
        # Test executing an ELF, not just writing files or running a shell script.
        if cp /bin/true "$work/exec-probe" && chmod +x "$work/exec-probe" && "$work/exec-probe"; then
            NATIVE_WORKSPACE="$work"
            NATIVE_WORKSPACES+=("$work")
            export NATIVE_WORKSPACE
            echo "Native workspace: $work ($(stat -f -c %T "$work" 2>/dev/null || echo unknown)); ${free_gb} GiB free"
            return 0
        fi
        echo "ELF execution failed in $work; trying another local filesystem." >&2
        # This path is the exact directory just created by mktemp.
        if [[ "$work" == "${parent%/}"/verus-native-* && ! -L "$work" ]]; then rm -rf -- "$work"; fi
    done
    echo "No executable scratch filesystem with ${required_gb} GiB free. Set CLUSTER_BUILD_TMP to node-local scratch (not HOME/CIFS and not /dev/shm)." >&2
    return 36
}

native_cleanup() {
    local work
    for work in "${NATIVE_WORKSPACES[@]}"; do
        # Only paths actually created and registered by native_workspace.
        if [[ -n "$work" && "${work##*/}" == verus-native-* && -d "$work" && ! -L "$work" ]]; then
            rm -rf -- "$work"
        fi
    done
}
declare -a NATIVE_WORKSPACES=()
