#!/usr/bin/env bash
set -euo pipefail
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
HIST=$ROOT/logs/continual_skill_core60_pilot_20261006
RUN=$ROOT/logs/rgbd_execution_capture_replay_v2_20261009
REPO=$HIST/runtime_repo
export ROOT CUDA_VISIBLE_DEVICES=0 MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
export LIBERO_CONFIG_PATH=$HIST/libero_config
export XLA_PYTHON_CLIENT_PREALLOCATE=false XLA_PYTHON_CLIENT_MEM_FRACTION=0.50
export PYTHONPATH=$REPO:$ROOT/third_party/LIBERO-PRO
export OMP_NUM_THREADS=2
export ORACLE_ENTRYPOINT=$HIST/core60_entrypoint.py
export ANCHOR_CAPTURE_DIR=$RUN/snapshots
export ANCHOR_DIAGNOSTIC_HOOK=$RUN/capture_support/visual_selection_oracle_geometry_hook.py
export ANCHOR_VISUAL_CODE=$RUN/visual_code
export ANCHOR_PROPRIO_HAND_STATE=1
export ANCHOR_RGBD_OBSTACLES=1
export ANCHOR_SAVE_REPLAY_FIXTURE=1
export ANCHOR_REPLACE_BOTTLE_GEOMETRY=1
export ANCHOR_REPLACE_PLATE_GEOMETRY=1
export CUTAMP_FLOCK_LOCK=$RUN/cutamp.lock
export CUTAMP_REAL_RUNNER=$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
cd "$REPO"
set +e
"$ROOT/envs/rlinf-openpi/bin/python" "$ROOT/logs/replay_anchor_recovery_20261009.py" --fixture "$ROOT/logs/rgbd_obstacle_recovery_20261009/replay_fixture" --bddl "$ROOT/logs/continual_skill_core60_pilot_20261006/bddl_files/libero_goal_task/put_the_bowl_on_the_plate.bddl" --run-dir "$RUN" --capture-every 5 --restore-open-gripper-command > "$RUN/driver.log" 2>&1
rc=$?
printf "%s\n" "$rc" > "$RUN/exitcode.txt"
exit "$rc"
