#!/usr/bin/env bash
set -euo pipefail
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
HIST=$ROOT/logs/continual_skill_core60_pilot_20261006
RUN=$ROOT/logs/oracle_anchor_rgbd_capture_20261009
REPO=$HIST/runtime_repo
export ROOT CUDA_VISIBLE_DEVICES=0 MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
export LIBERO_CONFIG_PATH=$HIST/libero_config
export XLA_PYTHON_CLIENT_PREALLOCATE=false XLA_PYTHON_CLIENT_MEM_FRACTION=0.50
export PYTHONPATH=$REPO:$ROOT/third_party/LIBERO-PRO
export OMP_NUM_THREADS=2
export ORACLE_ENTRYPOINT=$HIST/core60_entrypoint.py
export ANCHOR_CAPTURE_DIR=$RUN/snapshots
export CUTAMP_FLOCK_LOCK=$RUN/cutamp.lock
export CUTAMP_REAL_RUNNER=$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
cd "$REPO"
set +e
timeout 1800 "$ROOT/envs/rlinf-openpi/bin/python" "$RUN/capture_support/capture_oracle_recovery_rgbd.py" \
 --pretrained_path "$ROOT/models/pi0_libero_openpi" --config_name pi0_libero \
 --task_suite_name libero_goal_task --task_ids 4 --num_trials_per_task 1 \
 --episode_index_start 0 --episode_seed_start 1 --seed 90 --policy_in_process --save_video \
 --openvla_repo_root "$REPO" --task_language_source bddl --engine_language_source bddl \
 --max_recovery_calls 2 --max_recovery_steps 200 --max_replans 1 \
 --log_dir "$RUN" --exp_name run --enable_mining_skills \
 --skill_pack "$HIST/checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918" \
 --use_real_cutamp_backend --real_cutamp_require_feasible --real_cutamp_curobo_plan \
 --real_cutamp_serialize_trajectories --prefer_real_cutamp_executable_plan \
 --require_real_cutamp_executable_plan --real_cutamp_grasp_dof 6 \
 --real_cutamp_runner_python "$HIST/cutamp_flock.sh" --real_cutamp_runner_timeout_sec 900 \
 --real_cutamp_debug_dir "$RUN/cutamp_debug" > "$RUN/driver.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$RUN/exitcode.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$RUN/finished_utc.txt"
exit "$rc"
