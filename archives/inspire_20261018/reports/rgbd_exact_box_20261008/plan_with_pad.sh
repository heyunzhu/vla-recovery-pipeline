#!/usr/bin/env bash
set -euo pipefail
WORK=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN=$WORK/logs/rgbd_exact_box_20261008
export PYTHONPATH=$RUN/pydeps:$RUN/code
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
export CUTAMP_ALLOW_START_COLLISION_ESCAPE=0
export CUTAMP_CONTACT_MODE_TARGET=0
export CUTAMP_START_ESCAPE_Z=0
cd "$RUN/code"
"$WORK/envs/tiptop-planning-py310/bin/python" "$RUN/plan_with_pad.py"
echo PLAN_PAD_DONE
