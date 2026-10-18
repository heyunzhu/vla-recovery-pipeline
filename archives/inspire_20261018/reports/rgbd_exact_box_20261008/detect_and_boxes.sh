#!/usr/bin/env bash
set -euo pipefail
WORK=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN=$WORK/logs/rgbd_exact_box_20261008
CODE=$RUN/code
export PYTHONPATH=$RUN/pydeps:$CODE
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
cd "$CODE"
"$WORK/envs/tiptop-planning-py310/bin/python" scripts/recovery/skill_pipeline/run_grounded_sam2_snapshot.py \
  "$RUN/snapshot/agentview" \
  --language-summary "$RUN/snapshot/summary.json" \
  --out-dir "$RUN/snapshot/detector" \
  --grounding-model-dir "$RUN/models/grounding-dino-tiny" \
  --sam2-model-dir "$RUN/models/sam2.1-hiera-tiny" \
  --device cuda
echo DETECT_DONE
"$WORK/envs/tiptop-planning-py310/bin/python" scripts/recovery/skill_pipeline/run_exact_box_task.py \
  --observation-dir "$RUN/snapshot/agentview" \
  --detector-dir "$RUN/snapshot/detector" \
  --summary-json "$RUN/snapshot/summary.json" \
  --out-dir "$RUN/result"
echo BOXES_DONE
