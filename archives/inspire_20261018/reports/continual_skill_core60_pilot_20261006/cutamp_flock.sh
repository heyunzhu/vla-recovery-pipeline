#!/usr/bin/env bash
set -euo pipefail
exec flock -x "${CUTAMP_FLOCK_LOCK}" "${CUTAMP_REAL_RUNNER}" "$@"
