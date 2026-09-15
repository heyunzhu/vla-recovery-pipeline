from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .run_spec import HarnessSpec, dump_spec_json, split_tasks
from ..skill_pack import resolve_skill_config


@dataclass(frozen=True)
class HarnessPaths:
    workspace_root: Path
    repo_root: Path
    python_bin: Path
    log_root: Path
    model_path: Path
    libero_config_path: Path
    libero_pythonpath_root: Path

    @classmethod
    def from_workspace(
        cls,
        workspace_root: str | Path,
        *,
        repo_root: str | Path | None = None,
        python_bin: str | Path | None = None,
        log_root: str | Path | None = None,
        model: str | Path | None = None,
        libero_config_path: str | Path | None = None,
        libero_pythonpath_root: str | Path | None = None,
    ) -> "HarnessPaths":
        workspace = Path(workspace_root)
        repo = Path(repo_root) if repo_root is not None else workspace / "vla-recovery-pipeline"
        python = Path(python_bin) if python_bin is not None else workspace / "envs/openpi_jax_py311/bin/python"
        logs = Path(log_root) if log_root is not None else workspace / "logs"
        cfg = Path(libero_config_path) if libero_config_path is not None else workspace / "libero_config"
        libero_py_root = (
            Path(libero_pythonpath_root)
            if libero_pythonpath_root is not None
            else workspace / "LIBERO_src"
        )
        model_path = resolve_model(workspace, model or "pi0_libero_openpi")
        return cls(
            workspace_root=workspace,
            repo_root=repo,
            python_bin=python,
            log_root=logs,
            model_path=model_path,
            libero_config_path=cfg,
            libero_pythonpath_root=libero_py_root,
        )

    def to_mapping(self) -> dict[str, str]:
        return {
            "workspace_root": str(self.workspace_root),
            "repo_root": str(self.repo_root),
            "python_bin": str(self.python_bin),
            "log_root": str(self.log_root),
            "model_path": str(self.model_path),
            "libero_config_path": str(self.libero_config_path),
            "libero_pythonpath_root": str(self.libero_pythonpath_root),
        }


@dataclass(frozen=True)
class LanePlan:
    name: str
    gpu: int
    tasks: list[int]

    @property
    def task_id_string(self) -> str:
        return ",".join(str(task) for task in self.tasks)


def resolve_model(workspace_root: Path, model: str | Path) -> Path:
    raw = Path(model)
    if raw.is_absolute() or len(str(raw.drive)) > 0:
        return raw
    return workspace_root / "models" / raw


def git_output(repo: Path, args: list[str]) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"unknown ({exc!r})"


def git_head(repo: Path) -> str:
    head = git_output(repo, ["rev-parse", "--short", "HEAD"])
    if not head.startswith("unknown"):
        return head
    synced = repo / ".synced_git_head"
    if synced.exists():
        marker = synced.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if marker and marker[0].strip():
            return marker[0].strip()
    return head


def git_status(repo: Path) -> str:
    return git_output(repo, ["status", "--porcelain=v1"])


def make_run_dir(spec: HarnessSpec, paths: HarnessPaths, *, timestamp: str | None = None, commit: str | None = None) -> Path:
    stamp = timestamp or time.strftime("%Y%m%d_%H%M%S")
    head = commit or git_head(paths.repo_root)
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in spec.name)
    return paths.log_root / f"{safe_name}_{head}_{stamp}"


def lane_plans(spec: HarnessSpec, commit: str) -> list[LanePlan]:
    plans: list[LanePlan] = []
    for gpu, tasks in split_tasks(spec.tasks, spec.gpus):
        task_range = f"{tasks[0]:02d}_{tasks[-1]:02d}" if len(tasks) > 1 else f"{tasks[0]:02d}"
        name = f"{spec.name}_tasks{task_range}_gpu{gpu}_{commit}"
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
        plans.append(LanePlan(name=safe, gpu=gpu, tasks=tasks))
    return plans


def _q(value: str | Path) -> str:
    return shlex.quote(str(value))


def _flag_line(flag: str, enabled: bool) -> str:
    return f"      {flag} \\\n" if enabled else ""


def _real_cutamp_preflight_block(enabled: bool) -> str:
    if not enabled:
        return ""
    return """preflight_real_cutamp_runner() {
  local rc=0
  local py310="${WORKSPACE}/envs/uv-python/cpython-3.10.21-linux-x86_64-gnu/bin/python3.10"
  local tiptop_root="${WORKSPACE}/envs/tiptop-planning-py310"
  local tiptop_site="${tiptop_root}/lib/python3.10/site-packages"
  local cutamp_root="${WORKSPACE}/third_party/cuTAMP"
  local curobo_root="${WORKSPACE}/third_party/curobo"

  echo "preflight_start_time=$(date -Is)"
  chmod +x "${CUTAMP_RUNNER_PYTHON}" 2>/dev/null || true

  for path in \
    "${CUTAMP_RUNNER_PYTHON}" \
    "${py310}" \
    "${tiptop_root}" \
    "${tiptop_site}" \
    "${cutamp_root}" \
    "${curobo_root}"; do
    if [ -e "${path}" ]; then
      echo "PREFLIGHT_OK ${path}"
    else
      echo "PREFLIGHT_MISSING ${path}"
      rc=1
    fi
  done

  if [ -x "${CUTAMP_RUNNER_PYTHON}" ]; then
    echo "PREFLIGHT_OK executable:${CUTAMP_RUNNER_PYTHON}"
  else
    echo "PREFLIGHT_MISSING executable:${CUTAMP_RUNNER_PYTHON}"
    rc=1
  fi

  if "${PY}" -c 'import os; from OpenGL import EGL; assert EGL.eglQueryString is not None; import mujoco; from mujoco.egl import GLContext; ctx = GLContext(16, 16); ctx.make_current(); print("PREFLIGHT_OK egl", flush=True); os._exit(0)'; then
    :
  else
    echo "PREFLIGHT_FAILED egl"
    rc=1
  fi

  echo "preflight_done_time=$(date -Is)"
  return "${rc}"
}

set +e
preflight_real_cutamp_runner > "${BASE}/real_cutamp_preflight.log" 2>&1
preflight_rc=$?
set -e
cat "${BASE}/real_cutamp_preflight.log"
if [ "${preflight_rc}" -ne 0 ]; then
  echo "all_done_time=$(date -Is)" | tee "${BASE}/all_done.txt"
  echo "global_exit_code=2" | tee -a "${BASE}/all_done.txt"
  echo "preflight_exit_code=${preflight_rc}" | tee -a "${BASE}/all_done.txt"
  exit 2
fi

"""


def render_launch_script(spec: HarnessSpec, paths: HarnessPaths, run_dir: Path, commit: str) -> str:
    real = spec.real_cutamp
    diagnostics = spec.diagnostic_signals
    skill_config = resolve_skill_config(
        skill_pack=spec.skill_pack or None,
        skill_index=spec.skill_index or None,
        repo=paths.repo_root,
        default_diagnostic_registry_path=paths.repo_root
        / "experiments"
        / "robot"
        / "libero"
        / "skill_pipeline"
        / "diagnostics"
        / "registry.yaml",
    )
    resolved_skill_index = skill_config.skill_index
    resolved_skill_pack = skill_config.skill_pack.root if skill_config.skill_pack else ""
    generated_benchmark_block = ""
    if spec.generated_benchmark_dir:
        generated_benchmark_block = f"""      --generated_benchmark_dir {shlex.quote(spec.generated_benchmark_dir)} \\
      --generated_split {shlex.quote(spec.generated_split)} \\
      --generated_task_ids "${{tasks}}" \\
"""
    skill_flag = ""
    if spec.skills == "online":
        skill_flag = "      --enable_skills \\\n"
    elif spec.skills == "mining":
        skill_flag = "      --enable_mining_skills \\\n"

    real_cutamp_block = ""
    if real.enabled:
        real_cutamp_block = f"""      --use_real_cutamp_backend \\
{_flag_line("      --real_cutamp_require_feasible", real.require_feasible)}      --real_cutamp_robot {shlex.quote(real.robot)} \\
      --real_cutamp_grasp_dof {real.grasp_dof} \\
      --real_cutamp_num_particles {real.num_particles} \\
      --real_cutamp_num_opt_steps {real.num_opt_steps} \\
      --real_cutamp_max_loop_dur {real.max_loop_dur} \\
{_flag_line("      --real_cutamp_curobo_plan", real.curobo_plan)}{_flag_line("      --real_cutamp_serialize_trajectories", real.serialize_trajectories)}{_flag_line("      --prefer_real_cutamp_executable_plan", real.prefer_executable_plan)}{_flag_line("      --require_real_cutamp_executable_plan", real.require_executable_plan)}      --real_cutamp_runner_python "${{CUTAMP_RUNNER_PYTHON}}" \\
      --real_cutamp_runner_timeout_sec {real.runner_timeout_sec} \\
      --real_cutamp_debug_dir "${{out}}/cutamp_debug" \\
      --real_cutamp_table_proxy_profile {shlex.quote(real.table_proxy_profile)} \\
      --real_cutamp_static_context_collision_mode {shlex.quote(real.static_context_collision_mode)}
"""
    diagnostic_signal_block = ""
    if diagnostics.enabled:
        registry = (
            shlex.quote(diagnostics.registry)
            if diagnostics.registry
            else '"${DIAGNOSTIC_SIGNAL_REGISTRY}"'
        )
        diagnostic_signal_block = (
            f"      --diagnostic_signal_registry {registry} \\\n"
            f"      --diagnostic_signal_statuses {shlex.quote(diagnostics.statuses_csv)} \\\n"
        )
    skill_source_block = ""
    if spec.skill_pack:
        skill_source_block += '      --skill_pack "${SKILL_PACK}" \\\n'
    skill_source_block += '      --skill_index "${SKILL_INDEX}" \\\n'

    lane_calls = "\n".join(
        f"run_lane {plan.gpu} {shlex.quote(plan.task_id_string)} {shlex.quote(plan.name)}"
        for plan in lane_plans(spec, commit)
    )
    save_video = _flag_line("      --save_video", spec.save_video)
    policy = _flag_line("      --policy_in_process", spec.policy_in_process)
    preflight_block = _real_cutamp_preflight_block(real.enabled)
    export_block = ""
    if spec.save_video and spec.export_annotated:
        export_block = """    if [ "${eval_rc}" -eq 0 ]; then
      "${PY}" "${REPO}/scripts/recovery/skill_pipeline/export_annotated_skill_pipeline_videos.py" \\
        --run-dir "${out}" \\
        --out-dir "${annotated}"
      echo "annotated_done_time=$(date -Is)"
    fi
"""

    return f"""#!/usr/bin/env bash
set -euo pipefail

WORKSPACE={_q(paths.workspace_root)}
REPO={_q(paths.repo_root)}
PY={_q(paths.python_bin)}
BASE={_q(run_dir)}
MODEL={_q(paths.model_path)}
LIBERO_CONFIG={_q(paths.libero_config_path)}
LIBERO_PYTHONPATH_ROOT={_q(paths.libero_pythonpath_root)}
NUM_TRIALS={spec.episodes_per_task}
COMMIT={shlex.quote(commit)}
PID_DIR="${{BASE}}/pids"
ARCHIVE_OFFLINE_SCAN_CORPUS={1 if spec.archive_offline_scan_corpus else 0}
OFFLINE_SCAN_CORPUS_ROOT={_q(spec.offline_scan_corpus_root)}
OFFLINE_SKILL_SCAN={1 if spec.offline_skill_scan else 0}
OFFLINE_SCAN_INCLUDE_HINTS={1 if spec.offline_scan_include_hints else 0}
SKILL_INDEX={_q(resolved_skill_index)}
SKILL_PACK={_q(resolved_skill_pack)}
PREDICATE_REGISTRY={_q(skill_config.predicate_registry or "")}
PREDICATE_ADAPTER={_q(skill_config.predicate_adapter or "")}
DIAGNOSTIC_SIGNAL_REGISTRY={_q(diagnostics.registry or skill_config.diagnostic_signal_registry or "")}
DIAGNOSTIC_SIGNAL_STATUSES={_q(diagnostics.statuses_csv if diagnostics.enabled else "")}
DIAGNOSTIC_PROVIDER_ROOT={_q(skill_config.skill_pack.root if skill_config.skill_pack else "")}

mkdir -p "${{BASE}}" "${{PID_DIR}}"
cd "${{REPO}}"

export HOME="${{WORKSPACE}}"
export LIBERO_CONFIG_PATH="${{LIBERO_CONFIG}}"
export XDG_CACHE_HOME="${{WORKSPACE}}/.cache"
export HF_HOME="${{WORKSPACE}}/.cache/huggingface"
export TORCH_HOME="${{WORKSPACE}}/.cache/torch"
export JAX_COMPILATION_CACHE_DIR="${{WORKSPACE}}/.cache/jax"
export MPLCONFIGDIR="${{WORKSPACE}}/.cache/matplotlib"
export CUDA_CACHE_PATH="${{WORKSPACE}}/.cache/nv"
export PYTHONPATH="${{LIBERO_PYTHONPATH_ROOT}}:${{WORKSPACE}}/openpi/src:${{REPO}}:${{PYTHONPATH:-}}"
export OPENVLA_OFT_ROOT="${{REPO}}"
export ROOT="${{WORKSPACE}}"
export OVERLAY_ROOT="${{REPO}}"
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
export LD_LIBRARY_PATH="${{WORKSPACE}}/envs/egl-shim:${{WORKSPACE}}/envs/sysroot/usr/lib/x86_64-linux-gnu:${{WORKSPACE}}/envs/egl-libs:${{LD_LIBRARY_PATH:-}}"
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1
export CUTAMP_RUNNER_PYTHON="${{REPO}}/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh"
chmod +x "${{CUTAMP_RUNNER_PYTHON}}" 2>/dev/null || true

{preflight_block}\
run_lane() {{
  local gpu="$1"
  local tasks="$2"
  local lane="$3"
  local out="${{BASE}}/${{lane}}"
  local annotated="${{out}}_annotated_recovery_marked"
  mkdir -p "${{out}}"
  (
    export CUDA_VISIBLE_DEVICES="${{gpu}}"
    echo "start_time=$(date -Is)"
    echo "repo=${{REPO}}"
    echo "commit=${{COMMIT}}"
    echo "run_dir=${{out}}"
    echo "annotated_dir=${{annotated}}"
    echo "task_suite_name={spec.task_suite_name}"
    echo "task_ids=${{tasks}}"
    echo "generated_benchmark_dir={spec.generated_benchmark_dir}"
    echo "generated_split={spec.generated_split}"
    echo "generated_task_ids=${{tasks}}"
    echo "num_trials=${{NUM_TRIALS}}"
    echo "cuda_visible_devices=${{CUDA_VISIBLE_DEVICES}}"
    echo "libero_config_path=${{LIBERO_CONFIG_PATH}}"
    echo "libero_pythonpath_root=${{LIBERO_PYTHONPATH_ROOT}}"
    echo "skill_index=${{SKILL_INDEX}}"
    echo "skill_pack=${{SKILL_PACK}}"
    echo "predicate_registry=${{PREDICATE_REGISTRY}}"
    echo "predicate_adapter=${{PREDICATE_ADAPTER}}"
    echo "diagnostic_signal_registry=${{DIAGNOSTIC_SIGNAL_REGISTRY}}"
    echo "diagnostic_signal_statuses=${{DIAGNOSTIC_SIGNAL_STATUSES}}"
    set +e
    "${{PY}}" -m experiments.robot.libero.skill_pipeline.runner \\
      --log_dir "${{BASE}}" \\
      --exp_name "${{lane}}" \\
      --openvla_repo_root "${{REPO}}" \\
      --config_name {shlex.quote(spec.config_name)} \\
      --pretrained_path "${{MODEL}}" \\
      --task_suite_name {shlex.quote(spec.task_suite_name)} \\
      --task_ids "${{tasks}}" \\
{generated_benchmark_block}\
      --num_trials_per_task "${{NUM_TRIALS}}" \\
      --action_chunk {spec.action_chunk} \\
      --num_steps_wait {spec.num_steps_wait} \\
      --seed {spec.seed} \\
      --max_recovery_calls {spec.effective_max_recovery_calls} \\
{save_video}{skill_flag}{skill_source_block}\
{diagnostic_signal_block}\
{policy}      --force_recovery_query {spec.force_recovery_query} \\
      --max_recovery_steps {spec.max_recovery_steps} \\
      --max_replans {spec.max_replans} \\
      --num_particles {spec.num_particles} \\
      --particle_iters {spec.particle_iters} \\
      --particle_lr {spec.particle_lr} \\
      --min_success_fraction {spec.min_success_fraction} \\
{real_cutamp_block}
    eval_rc=$?
    set -e
    echo "eval_done_time=$(date -Is)"
    echo "eval_exit_code=${{eval_rc}}"
    echo "${{eval_rc}}" > "${{BASE}}/${{lane}}.exitcode"
{export_block}    exit "${{eval_rc}}"
  ) > "${{out}}/runner_and_export.log" 2>&1 &
  echo "$!" > "${{PID_DIR}}/${{lane}}.pid"
}}

{lane_calls}

rc=0
for pidfile in "${{PID_DIR}}"/*.pid; do
  pid=$(tr -d '\\r\\n' < "${{pidfile}}")
  if ! wait "${{pid}}"; then
    rc=1
  fi
done

echo "all_done_time=$(date -Is)" | tee "${{BASE}}/all_done.txt"
echo "global_exit_code=${{rc}}" | tee -a "${{BASE}}/all_done.txt"
post_rc=0
echo "postprocess_start_time=$(date -Is)" | tee -a "${{BASE}}/all_done.txt"

if ! "${{PY}}" "${{REPO}}/scripts/recovery/skill_pipeline/harness_report.py" --run_dir "${{BASE}}"; then
  post_rc=1
fi

if [ "${{ARCHIVE_OFFLINE_SCAN_CORPUS}}" = "1" ]; then
  if ! "${{PY}}" "${{REPO}}/scripts/recovery/skill_pipeline/archive_offline_scan_corpus.py" \\
    --run-dir "${{BASE}}" \\
    --repo "${{REPO}}" \\
    --corpus-root "${{OFFLINE_SCAN_CORPUS_ROOT}}" \\
    --name "${{BASE##*/}}"; then
    post_rc=1
  fi
fi

if [ "${{OFFLINE_SKILL_SCAN}}" = "1" ]; then
  scan_args=()
  if [ "${{OFFLINE_SCAN_INCLUDE_HINTS}}" != "1" ]; then
    scan_args+=(--no-hints)
  fi
  if [ -n "${{SKILL_PACK}}" ]; then
    scan_args+=(--skill-pack "${{SKILL_PACK}}")
  fi
  if [ -n "${{PREDICATE_REGISTRY}}" ]; then
    scan_args+=(--predicate-registry "${{PREDICATE_REGISTRY}}")
  fi
  if [ -n "${{PREDICATE_ADAPTER}}" ]; then
    scan_args+=(--predicate-adapter "${{PREDICATE_ADAPTER}}")
  fi
  if [ -n "${{DIAGNOSTIC_SIGNAL_REGISTRY}}" ]; then
    scan_args+=(--diagnostic-signal-registry "${{DIAGNOSTIC_SIGNAL_REGISTRY}}")
  fi
  if [ -n "${{DIAGNOSTIC_SIGNAL_STATUSES}}" ]; then
    scan_args+=(--diagnostic-signal-statuses "${{DIAGNOSTIC_SIGNAL_STATUSES}}")
  fi
  if [ -n "${{DIAGNOSTIC_PROVIDER_ROOT}}" ]; then
    scan_args+=(--diagnostic-provider-root "${{DIAGNOSTIC_PROVIDER_ROOT}}")
  fi
  if ! "${{PY}}" "${{REPO}}/scripts/recovery/skill_pipeline/scan_skill_triggers.py" \\
    --run-dir "${{BASE}}" \\
    --index "${{SKILL_INDEX}}" \\
    --out-dir "${{BASE}}/offline_skill_scan" \\
    "${{scan_args[@]}}"; then
    post_rc=1
  fi
fi

echo "postprocess_done_time=$(date -Is)" | tee -a "${{BASE}}/all_done.txt"
echo "postprocess_exit_code=${{post_rc}}" | tee -a "${{BASE}}/all_done.txt"
if [ "${{post_rc}}" -ne 0 ]; then
  rc=1
fi
exit "${{rc}}"
"""


def prepare_run(spec: HarnessSpec, paths: HarnessPaths, *, run_dir: Path | None = None) -> dict[str, Any]:
    commit = git_head(paths.repo_root)
    target = run_dir or make_run_dir(spec, paths, commit=commit)
    target.mkdir(parents=True, exist_ok=True)
    launch = target / "launch_harness.sh"
    launch.write_text(render_launch_script(spec, paths, target, commit), encoding="utf-8")
    try:
        launch.chmod(0o755)
    except OSError:
        pass
    dump_spec_json(spec, target / "resolved_spec.json")
    (target / "paths.json").write_text(json.dumps(paths.to_mapping(), indent=2), encoding="utf-8")
    (target / "git_head.txt").write_text(commit + "\n", encoding="utf-8")
    (target / "git_status.txt").write_text(git_status(paths.repo_root) + "\n", encoding="utf-8")
    (target / "lanes.json").write_text(
        json.dumps([plan.__dict__ for plan in lane_plans(spec, commit)], indent=2), encoding="utf-8"
    )
    return {
        "run_dir": str(target),
        "launch_script": str(launch),
        "commit": commit,
        "lanes": [plan.__dict__ for plan in lane_plans(spec, commit)],
    }


def start_run(run_dir: str | Path) -> int:
    target = Path(run_dir)
    launch = target / "launch_harness.sh"
    log = (target / "launcher.log").open("ab")
    proc = subprocess.Popen(["bash", str(launch)], cwd=str(target), stdout=log, stderr=subprocess.STDOUT)
    (target / "launcher.pid").write_text(str(proc.pid) + "\n", encoding="utf-8")
    return int(proc.pid)
