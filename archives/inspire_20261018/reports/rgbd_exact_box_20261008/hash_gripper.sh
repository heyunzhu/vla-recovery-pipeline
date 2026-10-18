#!/usr/bin/env bash
set -euo pipefail
RS=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/rlinf-openpi/lib/python3.11/site-packages/robosuite
find "$RS" -name 'panda_gripper.xml' -o -name 'hand.stl' -o -name 'finger*.stl' | head -40
XML=$(find "$RS" -name 'panda_gripper.xml' | head -1)
echo XML "$XML"
if [ -n "$XML" ]; then sha256sum "$XML"; fi
echo HASH_DONE
