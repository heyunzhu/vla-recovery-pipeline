#!/usr/bin/env bash
set -euo pipefail

ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN_ROOT="$ROOT/logs/continual_skill_core60_pilot_20261006"
REPO="$RUN_ROOT/runtime_repo"
PYTHON="$ROOT/envs/rlinf-openpi/bin/python"
MODEL="$ROOT/models/pi0_libero_openpi"
LIBERO_PRO="$ROOT/third_party/LIBERO-PRO"

run_worker() {
  local worker="$1"
  local WORKER_DIR="$RUN_ROOT/resume_workers/worker${worker}"
  mkdir -p "$WORKER_DIR"
  export ROOT CUDA_VISIBLE_DEVICES=0 MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
  export LIBERO_CONFIG_PATH="$RUN_ROOT/libero_config"
  export XLA_PYTHON_CLIENT_PREALLOCATE=false
  export XLA_PYTHON_CLIENT_MEM_FRACTION=0.50
  export PYTHONPATH="$REPO:$LIBERO_PRO"
  export OMP_NUM_THREADS=2
  export CUTAMP_FLOCK_LOCK="$RUN_ROOT/cutamp.lock"
  export CUTAMP_REAL_RUNNER="$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh"

  while IFS=$'\t' read -r job_id job_worker output_lane condition suite pack; do
    [[ "$job_id" == "job_id" ]] && continue
    [[ "$job_worker" != "$worker" ]] && continue
    local job_dir="$RUN_ROOT/lanes/lane${output_lane}/${job_id}_${condition}_${suite}"
    mkdir -p "$job_dir"
    [[ -f "$job_dir/.done" ]] && continue
    rm -f "$job_dir/.failed"
    printf '%s START job=%s condition=%s suite=%s output_lane=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$job_id" "$condition" "$suite" "$output_lane" | tee -a "$WORKER_DIR/worker.log"

    local common=(
      --pretrained_path "$MODEL"
      --config_name pi0_libero
      --task_suite_name "$suite"
      --task_ids 1,2,3,4,5,6,7,8,9,10
      --num_trials_per_task 5
      --episode_seed_start 1
      --seed 90
      --policy_in_process
      --save_video
      --openvla_repo_root "$REPO"
      --task_language_source bddl
      --engine_language_source bddl
      --max_recovery_calls 2
      --max_recovery_steps 200
      --max_replans 1
      --log_dir "$job_dir"
      --exp_name run
    )
    local extra=()
    if [[ "$condition" != "BASELINE" ]]; then
      extra=(
        --enable_mining_skills
        --skill_pack "$RUN_ROOT/checkpoints/$pack"
        --use_real_cutamp_backend
        --real_cutamp_require_feasible
        --real_cutamp_curobo_plan
        --real_cutamp_serialize_trajectories
        --prefer_real_cutamp_executable_plan
        --require_real_cutamp_executable_plan
        --real_cutamp_grasp_dof 6
        --real_cutamp_runner_python "$RUN_ROOT/cutamp_flock.sh"
        --real_cutamp_runner_timeout_sec 900
        --real_cutamp_debug_dir "$job_dir/cutamp_debug"
      )
    fi
    set +e
    "$PYTHON" "$RUN_ROOT/core60_entrypoint.py" "${common[@]}" "${extra[@]}" > "$job_dir/driver.log" 2>&1
    local rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
      printf '%s FAIL job=%s rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$job_id" "$rc" | tee -a "$WORKER_DIR/worker.log"
      echo "$rc" > "$job_dir/.failed"
      exit "$rc"
    fi
    touch "$job_dir/.done"
    printf '%s DONE job=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$job_id" | tee -a "$WORKER_DIR/worker.log"
  done < "$RUN_ROOT/resume_jobs.tsv"
}

case "${1:-}" in
  worker)
    run_worker "${2:?worker number required}"
    ;;
  *)
    echo "usage: $0 worker N" >&2
    exit 2
    ;;
esac
