#!/usr/bin/env bash
set -euo pipefail
BASE=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
for p in \
  "$BASE/envs/tiptop-planning-py310/lib/python3.10/site-packages/robosuite" \
  "$BASE/envs/rlinf-openpi/lib/python3.11/site-packages/robosuite" \
  "$BASE/third_party"
do
  if [ -d "$p" ]; then echo PRESENT "$p"; else echo MISSING "$p"; fi
done
find "$BASE/envs" -maxdepth 5 -name 'panda_gripper.xml' 2>/dev/null | head
find "$BASE/logs/rgbd_exact_box_20261008" -maxdepth 3 -name 'manifest.json' 2>/dev/null | head
echo SEARCH_DONE
