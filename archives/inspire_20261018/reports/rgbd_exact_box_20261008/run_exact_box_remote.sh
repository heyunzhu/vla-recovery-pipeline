#!/usr/bin/env bash
set -uo pipefail
WORK=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
SSD=/inspire/ssd/project/feelingai/chenwenming-25012/jxs/xinghanbo
BASE=$WORK/logs/libero_pro_six_suite_pack36_20260930
RUN=$WORK/logs/rgbd_exact_box_20261008
CODE=$RUN/code
PY=$WORK/envs/rlinf-openpi/bin/python
CUTAMP=$WORK/envs/tiptop-planning-py310/bin/python
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
export LD_LIBRARY_PATH=$WORK/envs/egl-shim:$WORK/envs/sysroot/usr/lib/x86_64-linux-gnu:$WORK/envs/egl-libs:${LD_LIBRARY_PATH:-}
export LIBERO_CONFIG_PATH=$BASE/libero_config
export LIBERO_PYTHONPATH_ROOT=$SSD/LIBERO-PRO
export PYTHONPATH=$BASE/pyshim:$SSD/LIBERO-PRO:$CODE
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
mkdir -p "$RUN"
cd "$CODE"

echo '==== PICK TASK ===='
"$PY" - << 'PY'
import json
from libero.libero import benchmark
from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
suites = ["libero_spatial", "libero_spatial_task", "libero_object", "libero_object_task", "libero_goal", "libero_goal_task"]
found = benchmark.get_benchmark_dict()
chosen = None
for name in suites:
    if name not in found:
        print("missing", name)
        continue
    suite = found[name]()
    language = str(suite.get_task(0).language)
    try:
        prompts = prompts_from_task_language(language)
    except ValueError as exc:
        print("skip", name, language, exc)
        continue
    goal = prompts
    print("ok", name, language, prompts)
    if chosen is None and "on" in language.lower():
        chosen = {"suite": name, "task_id": 0, "language": language}
if chosen is None:
    raise SystemExit("no place-on task parsed")
print("CHOSEN", json.dumps(chosen))
open("/tmp/rgbd_task_choice.json","w").write(json.dumps(chosen))
PY

echo '==== CAPTURE ===='
CHOICE=$("$PY" -c 'import json;print(json.load(open("/tmp/rgbd_task_choice.json"))["suite"])')
"$PY" scripts/recovery/skill_pipeline/collect_rgbd_snapshot.py \
  --task-suite-name "$CHOICE" --task-id 0 --init-index 0 --seed 7 \
  --resolution 256 --settle-steps 10 \
  --out-dir "$RUN/snapshot"

echo '==== MODELS ===='
export PYTHONPATH=$RUN/pydeps:$PYTHONPATH
if ! "$CUTAMP" -c 'import transformers,huggingface_hub' 2>/dev/null; then
  "$CUTAMP" -m pip install --target "$RUN/pydeps" 'transformers>=4.49' 'huggingface_hub' 'safetensors' 'tokenizers'
fi
"$CUTAMP" - << 'PY'
import torch
print("torch", torch.__version__, torch.cuda.is_available(), torch.__file__)
PY
export HF_HUB_DISABLE_XET=1
if [ ! -f "$RUN/models/grounding-dino-tiny/model.safetensors" ]; then
  "$CUTAMP" - << PY
import os
from huggingface_hub import snapshot_download
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
snapshot_download("IDEA-Research/grounding-dino-tiny", revision="a2bb814dd30d776dcf7e30523b00659f4f141c71", local_dir="$RUN/models/grounding-dino-tiny")
snapshot_download("facebook/sam2.1-hiera-tiny", revision="de431c4043854a71d8101e17995dfe596bf101a5", local_dir="$RUN/models/sam2.1-hiera-tiny")
print("models_ready")
PY
fi

echo '==== DETECT ===='
export PYTHONPATH=$RUN/pydeps:$CODE:${PYTHONPATH}
"$CUTAMP" scripts/recovery/skill_pipeline/run_grounded_sam2_snapshot.py \
  "$RUN/snapshot/agentview" \
  --language-summary "$RUN/snapshot/summary.json" \
  --out-dir "$RUN/snapshot/detector" \
  --grounding-model-dir "$RUN/models/grounding-dino-tiny" \
  --sam2-model-dir "$RUN/models/sam2.1-hiera-tiny" \
  --device cuda

echo '==== BOXES ===='
"$CUTAMP" scripts/recovery/skill_pipeline/run_exact_box_task.py \
  --observation-dir "$RUN/snapshot/agentview" \
  --detector-dir "$RUN/snapshot/detector" \
  --summary-json "$RUN/snapshot/summary.json" \
  --out-dir "$RUN/result"
echo DONE
