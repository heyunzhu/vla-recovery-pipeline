#!/usr/bin/env bash
set -euo pipefail
WORK=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
SSD=/inspire/ssd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN=$WORK/logs/rgbd_exact_box_20261008
export LIBERO_CONFIG_PATH=$RUN/libero_config
export LIBERO_PYTHONPATH_ROOT=$SSD/LIBERO-PRO
export PYTHONPATH=$RUN/code:$SSD/LIBERO-PRO
export PYTHONUNBUFFERED=1
"$WORK/envs/rlinf-openpi/bin/python" "$RUN/list_tasks.py"
