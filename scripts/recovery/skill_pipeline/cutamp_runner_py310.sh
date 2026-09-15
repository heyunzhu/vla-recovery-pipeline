#!/usr/bin/env bash
set -euo pipefail

ROOT="/mnt/nas/gezuhao/xinghanbo"
PY="$ROOT/envs/uv-python/cpython-3.10.21-linux-x86_64-gnu/bin/python3.10"
TIPTOP_SITE="$ROOT/envs/tiptop-planning-py310/lib/python3.10/site-packages"

export PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT/third_party/cuTAMP:$ROOT/third_party/curobo/src:$ROOT/openvla-oft:$TIPTOP_SITE:$TIPTOP_SITE/rerun_sdk:${PYTHONPATH:-}"

exec "$PY" "$@"
