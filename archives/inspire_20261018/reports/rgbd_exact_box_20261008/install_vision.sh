#!/usr/bin/env bash
set -euo pipefail
WORK=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
export RUN=$WORK/logs/rgbd_exact_box_20261008
PY=$WORK/envs/tiptop-planning-py310/bin/python
"$PY" -m pip install --target "$RUN/pydeps" --no-deps \
  torchvision==0.22.1 \
  --index-url https://download.pytorch.org/whl/cu126
"$PY" - << 'PY'
import os, sys
sys.path.insert(0, os.environ["RUN"] + "/pydeps")
import torch, torchvision
print("torch", torch.__version__, torch.cuda.is_available())
print("vision", torchvision.__version__)
PY
echo VISION_DONE
