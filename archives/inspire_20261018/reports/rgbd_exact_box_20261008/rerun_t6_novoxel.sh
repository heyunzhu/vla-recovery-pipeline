#!/usr/bin/env bash
set -euo pipefail
WORK=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN=$WORK/logs/rgbd_exact_box_20261008
CODE=$RUN/code
export PYTHONPATH=$RUN/pydeps:$CODE
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
cd "$CODE"
"$WORK/envs/tiptop-planning-py310/bin/python" scripts/recovery/skill_pipeline/run_exact_box_task.py \
  --observation-dir "$RUN/snapshot_t6/agentview" \
  --detector-dir "$RUN/snapshot_t6/detector_manual" \
  --summary-json "$RUN/snapshot_t6/summary.json" \
  --out-dir "$RUN/result_t6_manual_novoxel" \
  --drop-unlabeled-boxes
echo BOXES_DONE
