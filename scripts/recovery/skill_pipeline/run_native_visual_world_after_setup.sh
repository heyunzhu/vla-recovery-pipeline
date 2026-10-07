#!/usr/bin/env bash
# Follow the existing personal installer; never restart it or run a GPU solver.
set -euo pipefail
personal_root=/mnt/sdb/24_yyx
setup_root="$personal_root/setup/rgbd-planner-20261007"
probe_root="$personal_root/setup/native-visual-world-20261007"
runtime_root="$probe_root/runtime"
mkdir -p "$probe_root"
exec >> "$probe_root/probe.log" 2>&1
finish() { result=$?; if [ "$result" -eq 0 ]; then printf 'complete\n' > "$probe_root/status.txt"; else printf 'failed exit=%s\n' "$result" > "$probe_root/status.txt"; fi; }
trap finish EXIT
printf 'waiting existing_installer\n' > "$probe_root/status.txt"
while true; do
    state=$(cat "$setup_root/status.txt")
    if [ "$state" = complete ]; then break; fi
    if [[ "$state" = failed* ]]; then printf 'Installer failed: %s\n' "$state"; exit 1; fi
    # Authoritative live process check, not only an old status file.
    if ! pgrep -u 24_yyx -f '^bash /mnt/sdb/24_yyx/setup/setup_rgbd_planner_personal_20261007.sh$' >/dev/null; then
        # Re-read once for the small completion/process-exit race.
        state=$(cat "$setup_root/status.txt")
        if [ "$state" = complete ]; then break; fi
        printf 'Installer handle missing with status: %s\n' "$state"; exit 1
    fi
    sleep 30
done
printf 'running native_cpu_world_probe\n' > "$probe_root/status.txt"
export CUDA_VISIBLE_DEVICES=''
export OMP_NUM_THREADS=2
export CUDA_HOME=/usr/local/cuda-12.8
export PATH="$CUDA_HOME/bin:$PATH"
cd "$runtime_root"
"$personal_root/envs/cutamp-rgbd-20261007/bin/python" scripts/recovery/skill_pipeline/probe_native_visual_world.py \
    --problem-json "$probe_root/problem.json" --out-file "$probe_root/result.json"
