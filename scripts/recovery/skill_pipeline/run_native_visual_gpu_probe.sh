#!/usr/bin/env bash
# A single bounded personal diagnostic; no simulator/environment execution.
set -euo pipefail
probe_root=/mnt/sdb/24_yyx/setup/native-visual-world-gpu-20261007
exec >> "$probe_root/gpu_probe.log" 2>&1
finish() { result=$?; if [ "$result" -eq 0 ]; then printf 'complete\n' > "$probe_root/gpu_status.txt"; else printf 'failed exit=%s\n' "$result" > "$probe_root/gpu_status.txt"; fi; }
trap finish EXIT
printf 'running bounded_native_gpu_probe\n' > "$probe_root/gpu_status.txt"
export OMP_NUM_THREADS=2
export MAX_JOBS=2
export CUDA_HOME=/usr/local/cuda-12.8
export PATH="$CUDA_HOME/bin:$PATH"
export TORCH_EXTENSIONS_DIR=/mnt/sdb/24_yyx/tmp/rgbd-torch-extensions
export XDG_CACHE_HOME=/mnt/sdb/24_yyx/tmp/rgbd-runtime-cache
cd "$probe_root/runtime"
timeout --signal=TERM --kill-after=15s 300s /mnt/sdb/24_yyx/envs/cutamp-rgbd-20261007/bin/python \
    scripts/recovery/skill_pipeline/probe_native_visual_planner.py --gpu 6 \
    --problem-json "$probe_root/problem.json" --cpu-result "$probe_root/result.json" \
    --out-file "$probe_root/gpu_result.json"
