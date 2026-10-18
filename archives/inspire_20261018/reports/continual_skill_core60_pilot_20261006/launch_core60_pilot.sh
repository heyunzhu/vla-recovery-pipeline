#!/usr/bin/env bash
set -euo pipefail

ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
SOURCE_REPO="$ROOT/worktrees/object-batch-20261004"
RUN_ROOT="$ROOT/logs/continual_skill_core60_pilot_20261006"
PYTHON="$ROOT/envs/rlinf-openpi/bin/python"
MODEL="$ROOT/models/pi0_libero_openpi"
LIBERO_PRO="$ROOT/third_party/LIBERO-PRO"
PREV_CONFIG="$ROOT/logs/pro_object_batch_20261004_mrs200/libero_config"

setup_run() {
  mkdir -p "$RUN_ROOT" "$RUN_ROOT/lanes" "$RUN_ROOT/checkpoints"

  if [[ ! -d "$RUN_ROOT/runtime_repo" ]]; then
    cp -a "$SOURCE_REPO" "$RUN_ROOT/runtime_repo"
  fi
  REPO="$RUN_ROOT/runtime_repo"

  if [[ ! -d "$RUN_ROOT/libero_config" ]]; then
    cp -a "$PREV_CONFIG" "$RUN_ROOT/libero_config"
  fi
  mkdir -p "$RUN_ROOT/bddl_files"
  local shared_bddl="$LIBERO_PRO/liberopro/liberopro/bddl_files"
  local suite
  for suite in libero_goal_swap libero_spatial_task libero_goal_task libero_object_task libero_object_swap; do
    ln -sfn "$shared_bddl/$suite" "$RUN_ROOT/bddl_files/$suite"
  done
  # spatial_swap changes the frozen init states while retaining the base spatial tasks/BDDL.
  ln -sfn "$shared_bddl/libero_spatial" "$RUN_ROOT/bddl_files/libero_spatial_swap"
  sed -i -E "s#^bddl_files:.*#bddl_files: $RUN_ROOT/bddl_files#" "$RUN_ROOT/libero_config/config.yaml"

  local packs=(
    libero_goal_task_from_goal_swap_v1_asrun_20260913_clean
    libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914_clean
    libero_goal_task_from_goal_swap_spatial_mining_base_20260914
    libero_spatial_swap_from_goal_task_mining_base_20260916
    libero_object_task_from_spatial_swap_mining_base_20260918
  )
  local pack
  for pack in "${packs[@]}"; do
    if [[ ! -d "$RUN_ROOT/checkpoints/$pack" ]]; then
      cp -a "$REPO/skill_packs/$pack" "$RUN_ROOT/checkpoints/$pack"
      sed -i -E 's/^(description: )(.*)$/description: "\2"/' "$RUN_ROOT/checkpoints/$pack/pack.yaml"
    fi
  done

  chmod +x "$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh"
  install -m 0755 "$0" "$RUN_ROOT/launch_core60_pilot.sh"
  install -m 0644 "$(dirname "$0")/core60_entrypoint.py" "$RUN_ROOT/core60_entrypoint.py"
  install -m 0755 "$ROOT/logs/pro_object_batch_20261004_mrs200/cutamp_flock.sh" "$RUN_ROOT/cutamp_flock.sh"

  {
    echo "created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "source_repo=$SOURCE_REPO"
    echo "source_head=$(git -C "$SOURCE_REPO" rev-parse HEAD)"
    echo "source_status_begin"
    git -C "$SOURCE_REPO" status --short
    echo "source_status_end"
    echo "python=$PYTHON"
    echo "model=$MODEL"
    echo "libero_pro=$LIBERO_PRO"
    echo "episodes_per_task=5"
    echo "episode_seed_start=1"
    echo "policy_seed=90"
  } > "$RUN_ROOT/run_environment.txt"

  find "$RUN_ROOT/checkpoints" -type f -print0 | sort -z | xargs -0 sha256sum > "$RUN_ROOT/checkpoint_sha256.txt"

  REPO="$REPO" RUN_ROOT="$RUN_ROOT" PYTHONPATH="$REPO:$LIBERO_PRO" "$PYTHON" - <<'PY' > "$RUN_ROOT/snapshot_audit.txt"
import os
from pathlib import Path
import yaml
from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config

root = Path(os.environ["RUN_ROOT"]) / "checkpoints"
for pack in sorted(p for p in root.iterdir() if p.is_dir()):
    cfg = resolve_skill_config(skill_pack=str(pack), repo=os.environ["REPO"])
    data = yaml.safe_load(cfg.skill_index.read_text(encoding="utf-8")) or {}
    skills = (data.get("online") or []) + (data.get("fail_only") or [])
    print(f"OK\t{pack.name}\tindexed_skills={len(skills)}\tindex={cfg.skill_index}")
PY

  {
    printf 'job_id\tlane\tcondition\tsuite\tpack\n'
    local conditions=(C0 C1 C2 C3 C4)
    local suites=(libero_goal_swap libero_spatial_task libero_goal_task libero_spatial_swap libero_object_task libero_object_swap)
    local idx=0 condition suite pack_name
    for condition in "${conditions[@]}"; do
      case "$condition" in
        C0) pack_name=${packs[0]} ;;
        C1) pack_name=${packs[1]} ;;
        C2) pack_name=${packs[2]} ;;
        C3) pack_name=${packs[3]} ;;
        C4) pack_name=${packs[4]} ;;
      esac
      for suite in "${suites[@]}"; do
        printf '%03d\t%d\t%s\t%s\t%s\n' "$idx" "$((idx % 4))" "$condition" "$suite" "$pack_name"
        idx=$((idx + 1))
      done
    done
    for suite in "${suites[@]}"; do
      printf '%03d\t%d\tBASELINE\t%s\t-\n' "$idx" "$((idx % 4))" "$suite"
      idx=$((idx + 1))
    done
  } > "$RUN_ROOT/jobs.tsv"

  rm -f "$RUN_ROOT/stop.requested"
  local lane
  for lane in 0 1 2 3; do
    mkdir -p "$RUN_ROOT/lanes/lane${lane}"
    nohup bash "$RUN_ROOT/launch_core60_pilot.sh" lane "$lane" \
      > "$RUN_ROOT/lanes/lane${lane}/supervisor.log" 2>&1 &
    echo "$!" > "$RUN_ROOT/lanes/lane${lane}/supervisor.pid"
  done
  echo "$RUN_ROOT"
}

run_lane() {
  local lane="$1"
  local REPO="$RUN_ROOT/runtime_repo"
  local LANE_DIR="$RUN_ROOT/lanes/lane${lane}"
  export ROOT CUDA_VISIBLE_DEVICES=0 MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
  export LIBERO_CONFIG_PATH="$RUN_ROOT/libero_config"
  export XLA_PYTHON_CLIENT_PREALLOCATE=false
  export XLA_PYTHON_CLIENT_MEM_FRACTION=0.50
  export PYTHONPATH="$REPO:$LIBERO_PRO"
  export OMP_NUM_THREADS=2
  export CUTAMP_FLOCK_LOCK="$RUN_ROOT/cutamp.lock"
  export CUTAMP_REAL_RUNNER="$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh"

  while IFS=$'\t' read -r job_id job_lane condition suite pack; do
    [[ "$job_id" == "job_id" ]] && continue
    [[ "$job_lane" != "$lane" ]] && continue
    [[ -f "$RUN_ROOT/stop.requested" ]] && exit 0
    local job_dir="$LANE_DIR/${job_id}_${condition}_${suite}"
    mkdir -p "$job_dir"
    [[ -f "$job_dir/.done" ]] && continue
    rm -f "$job_dir/.failed"
    printf '%s START job=%s condition=%s suite=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$job_id" "$condition" "$suite" | tee -a "$LANE_DIR/lane.log"

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
      printf '%s FAIL job=%s rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$job_id" "$rc" | tee -a "$LANE_DIR/lane.log"
      echo "$rc" > "$job_dir/.failed"
      exit "$rc"
    fi
    touch "$job_dir/.done"
    printf '%s DONE job=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$job_id" | tee -a "$LANE_DIR/lane.log"
  done < "$RUN_ROOT/jobs.tsv"
}

case "${1:-setup}" in
  setup)
    setup_run
    ;;
  lane)
    run_lane "${2:?lane number required}"
    ;;
  *)
    echo "usage: $0 [setup|lane N]" >&2
    exit 2
    ;;
esac
