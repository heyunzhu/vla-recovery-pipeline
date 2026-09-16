#!/usr/bin/env bash
set -euo pipefail
# libero_spatial_swap task05 lane launcher. mrs=200 campaign standard.
# Usage: bash launch_ss_t05_lane.sh <gpu> <exp_name> <num_trials> <pack_path> <mining:0|1> <max_recovery_calls> <max_recovery_steps>
GPU=$1; EXP=$2; N=$3; PACK=$4; MINING=$5; MRC=$6; MRS=$7
RUN_ROOT=/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task05_newtree_20260916
REPO=/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706
PY=/mnt/nas/gezuhao/xinghanbo/envs/openpi_jax_py311/bin/python
MODEL=/mnt/nas/gezuhao/xinghanbo/models/pi0_libero_openpi
LP=/mnt/nas/gezuhao/xinghanbo/LIBERO-PRO
EXTRA=()
if [ "$MINING" = "1" ]; then EXTRA+=(--enable_mining_skills); fi
mkdir -p "$RUN_ROOT/libero_config"
cat > "$RUN_ROOT/libero_config/config.yaml" <<'EOF'
benchmark_root: /mnt/nas/gezuhao/xinghanbo/LIBERO-PRO/libero/libero
bddl_files: /mnt/nas/gezuhao/xinghanbo/LIBERO-PRO/libero/libero/bddl_files
init_states: /mnt/nas/gezuhao/xinghanbo/LIBERO-PRO/libero/libero/init_files
datasets: /mnt/nas/gezuhao/xinghanbo/libero_dataset
assets: /mnt/nas/gezuhao/xinghanbo/LIBERO-PRO/libero/libero/assets
EOF
cd "$REPO"
CUDA_VISIBLE_DEVICES=$GPU \
LIBERO_CONFIG_PATH="$RUN_ROOT/libero_config" \
PYTHONPATH="$LP:$REPO" \
MUJOCO_GL=egl \
timeout 10800 "$PY" scripts/recovery/skill_pipeline/run_skill_eval.py \
  --log_dir "$RUN_ROOT" \
  --exp_name "$EXP" \
  --config_name pi0_libero \
  --pretrained_path "$MODEL" \
  --task_suite_name libero_spatial_swap \
  --task_ids 5 \
  --num_trials_per_task "$N" \
  --episode_seed_start 51 \
  --seed 51 \
  --max_recovery_calls "$MRC" \
  --max_recovery_steps "$MRS" \
  --save_video --fps 10 \
  --skill_pack "$PACK" \
  "${EXTRA[@]}" \
  --policy_in_process \
  --use_real_cutamp_backend \
  --real_cutamp_require_feasible \
  --real_cutamp_grasp_dof 6 \
  --real_cutamp_num_particles 64 \
  --real_cutamp_num_opt_steps 40 \
  --real_cutamp_max_loop_dur 20.0 \
  --real_cutamp_curobo_plan \
  --real_cutamp_serialize_trajectories \
  --prefer_real_cutamp_executable_plan \
  --require_real_cutamp_executable_plan \
  --real_cutamp_runner_python "$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh" \
  --real_cutamp_runner_timeout_sec 360.0 \
  --real_cutamp_debug_dir "$RUN_ROOT/$EXP/cutamp_debug" \
  --real_cutamp_table_proxy_profile thin_clipped_lowered \
  --real_cutamp_static_context_collision_mode all \
  --real_cutamp_initial_state_min_confidence 0.6 \
  --openvla_repo_root "$REPO" \
  --task_language_source bddl \
  --engine_language_source bddl \
  > "$RUN_ROOT/$EXP.log" 2>&1
echo "EXIT=$?"