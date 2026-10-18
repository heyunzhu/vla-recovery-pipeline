#!/usr/bin/env bash
set -euo pipefail
WORK=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
SSD=/inspire/ssd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN=$WORK/logs/rgbd_exact_box_20261008
CODE=$RUN/code
SNAP=$RUN/snapshot_t6
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
export LD_LIBRARY_PATH=$WORK/envs/egl-shim:$WORK/envs/sysroot/usr/lib/x86_64-linux-gnu:$WORK/envs/egl-libs:${LD_LIBRARY_PATH:-}
export LIBERO_CONFIG_PATH=$RUN/libero_config
export LIBERO_PYTHONPATH_ROOT=$SSD/LIBERO-PRO
export PYTHONPATH=$CODE:$SSD/LIBERO-PRO
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
cd "$CODE"
"$WORK/envs/rlinf-openpi/bin/python" scripts/recovery/skill_pipeline/collect_rgbd_snapshot.py \
  --task-suite-name libero_spatial \
  --task-id 6 \
  --init-index 0 \
  --seed 7 \
  --resolution 256 \
  --settle-steps 10 \
  --out-dir "$SNAP"
echo CAPTURE_DONE
export PYTHONPATH=$RUN/pydeps:$CODE
"$WORK/envs/tiptop-planning-py310/bin/python" scripts/recovery/skill_pipeline/run_grounded_sam2_snapshot.py \
  "$SNAP/agentview" \
  --language-summary "$SNAP/summary.json" \
  --out-dir "$SNAP/detector" \
  --grounding-model-dir "$RUN/models/grounding-dino-tiny" \
  --sam2-model-dir "$RUN/models/sam2.1-hiera-tiny" \
  --device cuda \
  --grounding-mode per_category
echo DETECT_DONE
"$WORK/envs/tiptop-planning-py310/bin/python" scripts/recovery/skill_pipeline/run_exact_box_task.py \
  --observation-dir "$SNAP/agentview" \
  --detector-dir "$SNAP/detector" \
  --summary-json "$SNAP/summary.json" \
  --out-dir "$RUN/result_t6"
echo BOXES_DONE
