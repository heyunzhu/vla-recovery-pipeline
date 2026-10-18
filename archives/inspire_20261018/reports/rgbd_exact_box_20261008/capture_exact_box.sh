#!/usr/bin/env bash
set -euo pipefail
WORK=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
SSD=/inspire/ssd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN=$WORK/logs/rgbd_exact_box_20261008
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
export LD_LIBRARY_PATH=$WORK/envs/egl-shim:$WORK/envs/sysroot/usr/lib/x86_64-linux-gnu:$WORK/envs/egl-libs:${LD_LIBRARY_PATH:-}
export LIBERO_CONFIG_PATH=$RUN/libero_config
export LIBERO_PYTHONPATH_ROOT=$SSD/LIBERO-PRO
export PYTHONPATH=$RUN/code:$SSD/LIBERO-PRO
export PYTHONUNBUFFERED=1
cd "$RUN/code"
"$WORK/envs/rlinf-openpi/bin/python" scripts/recovery/skill_pipeline/collect_rgbd_snapshot.py \
  --task-suite-name libero_spatial \
  --task-id 0 \
  --init-index 0 \
  --seed 7 \
  --resolution 256 \
  --settle-steps 10 \
  --out-dir "$RUN/snapshot"
echo CAPTURE_DONE
