#!/usr/bin/env bash
set -euo pipefail
LOG=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/plan_pad.log
python3 - <<'PY' || /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/tiptop-planning-py310/bin/python - <<'PY'
from pathlib import Path
text=Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/plan_pad.log").read_text(errors="replace")
lines=[]
for raw in text.splitlines():
    line=raw.split("\r")[-1].strip()
    if not line or "it/s" in line or line.startswith("Loss:"):
        continue
    lines.append(line)
print("LINECOUNT", len(lines))
for line in lines[:80]:
    print(line[:400])
print("---TAIL---")
for line in lines[-30:]:
    print(line[:400])
PY
