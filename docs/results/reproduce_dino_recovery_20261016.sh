#!/usr/bin/env bash
set -euo pipefail
# Run on xinghanbo-eval; requires the preserved frozen assets from the report.
# The output directory must be unused.
RUN="${1:?Pass an unused absolute output directory}"
mkdir -- "$RUN"
cp -a /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_dino_integration_20261016/anchor_ownership8_640/capture_support "$RUN/capture_support"
cp /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_dino_integration_20261016/anchor_ownership8_640/distractor_prompts.json "$RUN/distractor_prompts.json"
export ANCHOR_CAPTURE_DIR="${RUN}/snapshots"
export ANCHOR_DIAGNOSTIC_HOOK="${RUN}/capture_support/visual_selection_oracle_geometry_hook.py"
export ANCHOR_EPISODE_ID=libero_goal_task:task04:ep00
export ANCHOR_PROPRIO_HAND_STATE=1
export ANCHOR_REPLACE_BOTTLE_GEOMETRY=1
export ANCHOR_REPLACE_PLATE_GEOMETRY=1
export ANCHOR_RGBD_OBSTACLES=1
export ANCHOR_VISUAL_CODE=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_dino_integration_20261016/code_ownership8
export ANCHOR_VISUAL_EXECUTOR=1
export ANCHOR_VISUAL_IDS=1
export CUDA_VISIBLE_DEVICES=0
export CUTAMP_FLOCK_LOCK="${RUN}/cutamp.lock"
export CUTAMP_REAL_RUNNER=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006/runtime_repo/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
export LIBERO_CONFIG_PATH=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006/libero_config
export MUJOCO_GL=egl
export OMP_NUM_THREADS=2
export ORACLE_ENTRYPOINT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006/core60_entrypoint.py
export PYOPENGL_PLATFORM=egl
export PYTHONPATH=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006/runtime_repo:/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/third_party/LIBERO-PRO
export ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
export XLA_PYTHON_CLIENT_MEM_FRACTION=0.50
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export ANCHOR_FINETUNED_DINO_EXPORT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_dino_integration_20261016/hf_export_best
export DINO_INFERENCE_PYTHON=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/tiptop-planning-py310/bin/python
export DINO_INFERENCE_PYTHONPATH=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_dino_integration_20261016/dino440_deps:/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/pydeps:/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_dino_integration_20261016/code_ownership8
cd /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006/runtime_repo
/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/rlinf-openpi/bin/python /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_dino_integration_20261016/code_ownership8/scripts/recovery/skill_pipeline/replay_anchor_recovery.py --fixture /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_ten_tasks_20261015/01_goal_bottle_plate/oracle/replay_fixture --bddl /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006/bddl_files/libero_goal_task/put_the_bowl_on_the_plate.bddl --run-dir "${RUN}" --capture-every 5 --restore-open-gripper-command --evaluation-done-only --camera-resolution 640 > "$RUN/driver.log" 2>&1
