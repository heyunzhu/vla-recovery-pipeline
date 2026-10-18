#!/usr/bin/env bash
set -euo pipefail
WORK=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
export RUN=$WORK/logs/rgbd_exact_box_20261008
export PYTHONPATH=$RUN/pydeps
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1
export HF_HUB_ETAG_TIMEOUT=120
export HF_HUB_DOWNLOAD_TIMEOUT=120
export PYTHONUNBUFFERED=1
mkdir -p "$RUN/models"
"$WORK/envs/tiptop-planning-py310/bin/python" - << 'PY'
import os
from huggingface_hub import snapshot_download
run = os.environ["RUN"]
pairs = [
    ("IDEA-Research/grounding-dino-tiny", "a2bb814dd30d776dcf7e30523b00659f4f141c71", "grounding-dino-tiny"),
    ("facebook/sam2.1-hiera-tiny", "de431c4043854a71d8101e17995dfe596bf101a5", "sam2.1-hiera-tiny"),
]
for repo, rev, name in pairs:
    dest = os.path.join(run, "models", name)
    print("DOWNLOAD", repo, flush=True)
    snapshot_download(repo, revision=rev, local_dir=dest)
    print("DONE", name, flush=True)
PY
echo MODELS_DONE
