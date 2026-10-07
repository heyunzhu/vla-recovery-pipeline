#!/usr/bin/env bash
set -euo pipefail
probe_root=/mnt/sdb/24_yyx/setup/native-visual-world-gpu-20261007
exec >> "$probe_root/initial_collision.log" 2>&1
finish() { result=$?; if [ "$result" -eq 0 ]; then printf 'complete\n' > "$probe_root/initial_collision_status.txt"; else printf 'failed exit=%s\n' "$result" > "$probe_root/initial_collision_status.txt"; fi; }
trap finish EXIT
printf 'running initial_collision_attribution\n' > "$probe_root/initial_collision_status.txt"
export OMP_NUM_THREADS=2 MAX_JOBS=2
export CUDA_HOME=/usr/local/cuda-12.8
export PATH="$CUDA_HOME/bin:$PATH"
export TORCH_EXTENSIONS_DIR=/mnt/sdb/24_yyx/tmp/rgbd-torch-extensions
export XDG_CACHE_HOME=/mnt/sdb/24_yyx/tmp/rgbd-runtime-cache
cd "$probe_root/runtime"
timeout --signal=TERM --kill-after=15s 300s /mnt/sdb/24_yyx/envs/cutamp-rgbd-20261007/bin/python \
    scripts/recovery/skill_pipeline/probe_native_initial_collision.py --gpu 6 \
    --problem-json "$probe_root/problem.json" --cpu-result "$probe_root/result.json" \
    --out-file "$probe_root/initial_collision_result.json"
