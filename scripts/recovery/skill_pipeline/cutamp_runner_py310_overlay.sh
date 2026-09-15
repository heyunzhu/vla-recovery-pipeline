#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
REPO_PARENT="$(cd "$REPO_ROOT/.." && pwd)"
if [[ "$(basename "$REPO_PARENT")" == "code" || "$(basename "$REPO_PARENT")" == "code_snapshots" ]]; then
  DEFAULT_ROOT="$(cd "$REPO_PARENT/.." && pwd)"
else
  DEFAULT_ROOT="$REPO_PARENT"
fi

ROOT=${ROOT:-$DEFAULT_ROOT}
OVERLAY_ROOT=${OVERLAY_ROOT:-}
if [[ -x "$ROOT/envs/uv-python/cpython-3.10.21-linux-x86_64-gnu/bin/python3.10" ]]; then
  PY="$ROOT/envs/uv-python/cpython-3.10.21-linux-x86_64-gnu/bin/python3.10"
else
  PY="$ROOT/envs/tiptop-planning-py310/bin/python"
fi
TIPTOP_SITE="$ROOT/envs/tiptop-planning-py310/lib/python3.10/site-packages"

export PYTHONNOUSERSITE=1
if [[ -n "${OVERLAY_ROOT}" ]]; then
  export PYTHONPATH="${OVERLAY_ROOT}:$ROOT/third_party/cuTAMP:$ROOT/third_party/curobo/src:$REPO_ROOT:$TIPTOP_SITE:$TIPTOP_SITE/rerun_sdk:${PYTHONPATH:-}"
else
  export PYTHONPATH="$ROOT/third_party/cuTAMP:$ROOT/third_party/curobo/src:$REPO_ROOT:$TIPTOP_SITE:$TIPTOP_SITE/rerun_sdk:${PYTHONPATH:-}"
fi

exec "$PY" "$@"
