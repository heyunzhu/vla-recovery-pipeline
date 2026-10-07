#!/usr/bin/env bash
# Run only inside the user's personal data directory; no global packages/GPU work.
set -euo pipefail
personal_root=/mnt/sdb/24_yyx
planner_env="$personal_root/envs/cutamp-rgbd-20261007"
planner_sources="$personal_root/projects/planning-vendor-20261007"
setup_root="$personal_root/setup/rgbd-planner-20261007"
status_path="$setup_root/status.txt"
mkdir -p "$setup_root"
exec >> "$setup_root/setup.log" 2>&1
finish() { result=$?; if [ "$result" -eq 0 ]; then printf 'complete\n' > "$status_path"; else printf 'failed exit=%s\n' "$result" > "$status_path"; fi; }
trap finish EXIT
printf 'running environment_setup\n' > "$status_path"
if [ ! -x "$planner_env/bin/python" ]; then
  "$personal_root/python/cpython-3.11.16-linux-x86_64-gnu/bin/python3.11" -m venv "$planner_env"
fi
export CUDA_HOME=/usr/local/cuda-12.8
export PATH="$CUDA_HOME/bin:$PATH"
export TORCH_CUDA_ARCH_LIST=8.9
export MAX_JOBS=2
export CUDA_VISIBLE_DEVICES=''
export OMP_NUM_THREADS=2
export PIP_CACHE_DIR="$personal_root/tmp/planner-pip-cache"
export TMPDIR="$personal_root/tmp/planner-build"
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR"
planner_python="$planner_env/bin/python"
"$planner_python" -m pip install --timeout 30 --retries 2 'pip>=25' setuptools wheel setuptools_scm ninja
printf 'running torch_install\n' > "$status_path"
"$planner_python" -m pip install --timeout 30 --retries 2 'torch==2.7.1' 'numpy<2' 'warp-lang<1.13'
printf 'running cutamp_dependencies\n' > "$status_path"
"$planner_python" -m pip install --timeout 30 --retries 2 -e "$planner_sources/cuTAMP"
printf 'running curobo_compile\n' > "$status_path"
# Sources are transferred as a pinned archive; provide version without a Git checkout.
SETUPTOOLS_SCM_PRETEND_VERSION=0.7.8 "$planner_python" -m pip install --timeout 30 --retries 2 --no-build-isolation -e "$planner_sources/curobo"
printf 'running import_probe\n' > "$status_path"
"$planner_python" - <<'PY'
import importlib.metadata,json
import cutamp,curobo,torch
report=dict(torch=torch.__version__,torch_cuda=torch.version.cuda,
            cutamp=importlib.metadata.version('cuTAMP'),curobo=importlib.metadata.version('nvidia_curobo'),
            gpu_work_started=False)
print(json.dumps(report,indent=2))
with open('/mnt/sdb/24_yyx/setup/rgbd-planner-20261007/import_probe.json','w') as stream:
    json.dump(report,stream,indent=2)
PY
