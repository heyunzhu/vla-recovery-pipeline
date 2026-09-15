"""Pi0 eval runner with the new episode layout. Skills are off by default.

This is the skill-pipeline entrypoint. Do not treat
`scripts/recovery/pi0_rolling_cutamp_recovery_eval_jax.py` as the new runner.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import logging
import math
import multiprocessing as mp
import os
import pathlib
import re
import sys
import traceback
from typing import Any

from .trace_schema import (
    EpisodeWriter,
    compact_holding,
    make_query_record,
    recover_without_execution_event,
    recovery_events_from_trace,
)
from .skill_pack import resolve_skill_config


LIBERO_DUMMY_ACTION = [0.0] * 6 + [-1.0]
LIBERO_ENV_RESOLUTION = 256
MAX_STEPS = {
    "libero_spatial": 240,
    "libero_object": 280,
    "libero_goal": 300,
    "libero_10": 520,
    "libero_90": 400,
}
LIBERO_PRO_UMBRELLA = "libero_pro"
LIBERO_PRO_EXCLUDED_SUITES = {
    "libero_10",
    "libero_90",
    "libero_100",
    "libero_goal",
    "libero_object",
    "libero_spatial",
}
LIBERO_PRO_DEFAULT_MAX_STEPS = 600
ARTICULATED_BLOCKER_OPEN_QPOS_THRESHOLD = 0.04
ARTICULATED_BLOCKER_CONTACT_MAX_DISTANCE_M = 0.003
ARTICULATED_BLOCKER_CONTACT_TRIGGER_QUERIES = 3
OPEN_CABINET_BOWL_PICK_TARGET_FAR_M = 0.12


def default_skills_index() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[4] / "skills" / "_index.yaml"


def default_diagnostic_signal_registry() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "diagnostics" / "registry.yaml"


def max_steps_for_suite(suite_name: str) -> int:
    suite = str(suite_name)
    if suite in MAX_STEPS:
        return MAX_STEPS[suite]
    if suite.startswith("libero_10_"):
        return MAX_STEPS["libero_10"]
    if suite.startswith("libero_goal_"):
        return MAX_STEPS["libero_goal"]
    if suite.startswith("libero_object_"):
        return MAX_STEPS["libero_object"]
    if suite.startswith("libero_spatial_"):
        return MAX_STEPS["libero_spatial"]
    if suite in {LIBERO_PRO_UMBRELLA, "libero_mine", "libero_study_table"}:
        return LIBERO_PRO_DEFAULT_MAX_STEPS
    if suite.startswith("libero_"):
        return LIBERO_PRO_DEFAULT_MAX_STEPS
    raise KeyError(f"unknown LIBERO task suite: {suite_name}")


def episode_seed_for_index(base_seed: int, episode_idx: int, episode_seed_start: int = 0) -> int:
    if int(episode_seed_start) > 0:
        return int(episode_seed_start) + int(episode_idx)
    return int(base_seed)


def init_state_index_for_episode(episode_idx: int, n_initial_states: int) -> int:
    if int(n_initial_states) <= 0:
        raise ValueError("LIBERO task has no initial states")
    return int(episode_idx) % int(n_initial_states)


def should_early_stop_first_failures(
    *,
    completed_episodes: int,
    successes: int,
    first_n_failures: int,
) -> bool:
    """Stop an obviously failing validation after the first N all fail."""
    threshold = int(first_n_failures or 0)
    return threshold > 0 and int(completed_episodes) >= threshold and int(successes) <= 0


def check_trigger_exclusivity(args: argparse.Namespace) -> None:
    if int(getattr(args, "episode_index_start", 0)) < 0:
        raise ValueError("--episode_index_start must be >= 0")
    residual = bool(getattr(args, "enable_residual_trigger", False))
    skills_on = bool(getattr(args, "enable_skills", False))
    mining_on = bool(getattr(args, "enable_mining_skills", False))
    explicit_skill_source = bool(
        str(getattr(args, "skill_pack", "") or "").strip()
        or str(getattr(args, "skill_index", "") or "").strip()
    )
    early_stop = int(getattr(args, "early_stop_first_n_failures", 0) or 0)
    if residual:
        raise ValueError(
            "Residual trigger baseline belongs on the old eval script; "
            "do not mix it into skill-pipeline evidence."
        )
    if skills_on and mining_on:
        raise ValueError("use only one of --enable_skills or --enable_mining_skills")
    if (skills_on or mining_on) and not explicit_skill_source:
        raise ValueError("skill-enabled runs require an explicit --skill_pack or --skill_index")
    if residual and (skills_on or mining_on) and not args.allow_trigger_ablation:
        raise ValueError("residual trigger and skill hooks cannot both be effective sources")
    if early_stop < 0:
        raise ValueError("--early_stop_first_n_failures must be >= 0")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser("Pi0 skill-pipeline eval (new traces, skills off by default).")
    parser.add_argument("--log_dir", type=str, default="logs")
    parser.add_argument("--exp_name", type=str, default="skill_pipeline_pi0")
    parser.add_argument("--config_name", type=str, default="pi0_libero")
    parser.add_argument("--pretrained_path", type=str, required=True)
    parser.add_argument("--task_suite_name", type=str, default="libero_90")
    parser.add_argument("--task_ids", type=str, default="")
    parser.add_argument(
        "--generated_benchmark_dir",
        type=str,
        default="",
        help="Generated LIBERO benchmark root. When set, read manifests/<split>_tasks.jsonl.",
    )
    parser.add_argument(
        "--generated_split",
        choices=["smoke", "train", "validation", "all"],
        default="smoke",
        help="Generated benchmark split to evaluate.",
    )
    parser.add_argument(
        "--generated_task_ids",
        type=str,
        default="",
        help="Comma-separated generated task ids, or 1-based row indices within the selected split.",
    )
    parser.add_argument("--num_trials_per_task", type=int, default=1)
    parser.add_argument("--episode_index_start", type=int, default=0,
                        help="Run a slice of the original episode order; preserves seed and init-state indices.")
    parser.add_argument(
        "--early_stop_first_n_failures",
        type=int,
        default=0,
        help=(
            "When >0, stop each task after this many completed episodes if all have failed. "
            "Mining validation uses this to return to Codex quickly for obviously bad drafts."
        ),
    )
    parser.add_argument("--action_chunk", type=int, default=5)
    parser.add_argument("--num_steps_wait", type=int, default=10)
    parser.add_argument("--seed", type=int, default=90)
    parser.add_argument(
        "--episode_seed_start",
        type=int,
        default=0,
        help=(
            "When >0, reseed each rollout as episode_seed_start + episode_idx and record that seed in traces. "
            "The LIBERO initial-state episode order is unchanged."
        ),
    )
    parser.add_argument("--max_recovery_calls", type=int, default=1)
    parser.add_argument("--save_video", action="store_true")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--enable_skills", action="store_true")
    parser.add_argument(
        "--enable_mining_skills",
        action="store_true",
        help="Load pair + fail_only drafts for offline mining validation. Never use as production --enable_skills.",
    )
    parser.add_argument(
        "--skill_pack",
        "--skill-pack",
        dest="skill_pack",
        type=str,
        default="",
        help="Optional isolated skill pack name/path. Explicit --skill_index/registry flags override pack defaults.",
    )
    parser.add_argument("--skill_index", type=str, default="")
    parser.add_argument(
        "--capability_registry",
        type=str,
        default="",
        help="Optional skill capability registry. If omitted, use capability_registry from --skill_index when present.",
    )
    parser.add_argument(
        "--diagnostic_signal_registry",
        type=str,
        default="",
        help="Diagnostic signal registry for draft/shadow qstate providers.",
    )
    parser.add_argument(
        "--predicate_registry",
        type=str,
        default="",
        help="Optional pack predicate registry for repair/applies_to matching.",
    )
    parser.add_argument(
        "--predicate_adapter",
        type=str,
        default="",
        help="Optional pack predicate adapter Python file.",
    )
    parser.add_argument(
        "--diagnostic_signal_statuses",
        type=str,
        default="",
        help="Comma-separated diagnostic signal statuses to compute, e.g. shadow or draft,shadow. Empty disables.",
    )
    parser.add_argument("--policy_in_process", action="store_true", help="Debug only; may conflict with MuJoCo/OSMesa.")
    parser.add_argument(
        "--force_recovery_query",
        type=int,
        default=-1,
        help="CLI contrast only; not a skill. If >= 0, enter recovery at this query.",
    )
    parser.add_argument("--enable_residual_trigger", action="store_true")
    parser.add_argument("--allow_trigger_ablation", action="store_true")
    parser.add_argument(
        "--openvla_repo_root",
        default=str(pathlib.Path(__file__).resolve().parents[4]),
        help="Repository root. The option name is retained for launch-command compatibility.",
    )
    parser.add_argument("--max_recovery_steps", type=int, default=80)
    parser.add_argument("--max_replans", type=int, default=1)
    parser.add_argument("--num_particles", type=int, default=128)
    parser.add_argument("--particle_iters", type=int, default=100)
    parser.add_argument("--particle_lr", type=float, default=0.045)
    parser.add_argument("--min_success_fraction", type=float, default=0.01)
    parser.add_argument("--use_real_cutamp_backend", action="store_true")
    parser.add_argument("--real_cutamp_require_feasible", action="store_true")
    parser.add_argument("--real_cutamp_robot", default="panda")
    parser.add_argument(
        "--real_cutamp_grasp_dof",
        type=int,
        choices=[4, 6],
        default=6,
        help=(
            "6 (default) installs the profile-driven grasp sampler, so --grasp_sampler_profile "
            "and pack grasp adapters decide how particles are sampled. 4 bypasses every "
            "non-native profile and samples particles with cuTAMP's native 4-DOF sampler; "
            "select the 'native' profile instead if a native baseline is what you want."
        ),
    )
    parser.add_argument("--real_cutamp_num_particles", type=int, default=64)
    parser.add_argument("--real_cutamp_num_opt_steps", type=int, default=40)
    parser.add_argument("--real_cutamp_max_loop_dur", type=float, default=20.0)
    parser.add_argument("--real_cutamp_curobo_plan", action="store_true")
    parser.add_argument("--real_cutamp_serialize_trajectories", action="store_true")
    parser.add_argument("--prefer_real_cutamp_executable_plan", action="store_true")
    parser.add_argument("--require_real_cutamp_executable_plan", action="store_true")
    parser.add_argument("--real_cutamp_runner_python", default=os.environ.get("CUTAMP_RUNNER_PYTHON", ""))
    parser.add_argument("--real_cutamp_runner_timeout_sec", type=float, default=240.0)
    parser.add_argument("--real_cutamp_debug_dir", default="")
    parser.add_argument(
        "--real_cutamp_table_proxy_profile",
        choices=["default", "thin_clipped_lowered"],
        default="thin_clipped_lowered",
    )
    parser.add_argument("--real_cutamp_table_x_min_clip", type=float, default=None)
    parser.add_argument("--real_cutamp_table_height_override", type=float, default=None)
    parser.add_argument("--real_cutamp_table_z_offset", type=float, default=None)
    parser.add_argument("--real_cutamp_no_table_collision_obstacle", action="store_true")
    parser.add_argument("--real_cutamp_static_context_collision_mode", choices=["all", "none"], default="all")
    parser.add_argument("--real_cutamp_no_dummy_obstacle_if_empty", action="store_true")
    parser.add_argument("--real_cutamp_disable_simulator_truth_initial_state", action="store_true")
    parser.add_argument("--real_cutamp_initial_state_min_confidence", type=float, default=0.60)
    parser.add_argument("--real_cutamp_allow_unsupported_holding", action="store_true")
    parser.add_argument("--real_cutamp_disable_initial_holding_prebinding", action="store_true")
    parser.add_argument("--recovery_goal_mode", choices=["default", "pick_only"], default="default")
    parser.add_argument(
        "--task_language_source",
        choices=["auto", "filename", "bddl"],
        default="auto",
        help="Source of the policy prompt. 'auto' keeps the historical filename prompt except "
        "on LIBERO-Pro *_task suites, where the BDDL (:language ...) is the checked goal.",
    )
    parser.add_argument(
        "--engine_language_source",
        choices=["auto", "policy", "bddl"],
        default="auto",
        help="Source of the recovery engine's task description. 'auto' follows the policy "
        "prompt except on LIBERO-Pro *_task suites, where it uses the BDDL language.",
    )
    args = parser.parse_args(argv)
    check_trigger_exclusivity(args)
    return args


def _quat2axisangle(quat):
    import numpy as np

    quat = np.asarray(quat).copy()
    quat[3] = np.clip(quat[3], -1.0, 1.0)
    den = math.sqrt(1.0 - quat[3] * quat[3])
    if math.isclose(float(den), 0.0):
        return np.zeros(3, dtype=np.float32)
    return (quat[:3] * 2.0 * math.acos(float(quat[3])) / den).astype(np.float32)


def _patch_torch_load() -> None:
    import torch

    original = torch.load

    def _legacy(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original(*args, **kwargs)

    torch.load = _legacy


class _ArrayWithNumpy:
    def __init__(self, value):
        import numpy as np

        self._value = np.asarray(value, dtype=np.float32)

    def numpy(self):
        return self._value


class _ModelState:
    def __init__(self):
        self.last_uncertainty_logvar = None


class JaxOpenPIUncertaintyPolicyAdapter:
    def __init__(self, config_name, checkpoint_dir):
        from openpi.training import config as _config
        from openpi.policies import policy_config

        cfg = _config.get_config(config_name)
        self._policy = policy_config.create_trained_policy(cfg, pathlib.Path(checkpoint_dir))
        self._model = _ModelState()

    def reset(self):
        if hasattr(self._policy, "reset"):
            self._policy.reset()
        self._model.last_uncertainty_logvar = None

    def infer(self, observation):
        import numpy as np

        out = self._policy.infer(observation)
        logvar = out.get("actions_log_var")
        if logvar is not None:
            arr = np.asarray(logvar, dtype=np.float32)
            if arr.ndim == 2:
                arr = arr[None, ...]
            self._model.last_uncertainty_logvar = _ArrayWithNumpy(arr)
        else:
            self._model.last_uncertainty_logvar = None
        return out


def _policy_worker(conn, config_name: str, checkpoint_dir: str) -> None:
    try:
        _patch_torch_load()
        policy = JaxOpenPIUncertaintyPolicyAdapter(config_name, checkpoint_dir)
        conn.send(("ready", None))
        while True:
            cmd, payload = conn.recv()
            if cmd == "close":
                conn.send(("ok", None))
                return
            if cmd == "reset":
                policy.reset()
                conn.send(("ok", None))
                continue
            if cmd == "infer":
                out = policy.infer(payload)
                logvar = getattr(policy._model.last_uncertainty_logvar, "numpy", lambda: None)()
                conn.send(("ok", {"output": out, "logvar": logvar}))
                continue
            raise ValueError(f"unknown policy worker command: {cmd}")
    except BaseException:
        conn.send(("error", traceback.format_exc()))


class SubprocessOpenPIUncertaintyPolicyAdapter:
    """Keep PyTorch/OpenPI model loading out of the MuJoCo render process."""

    def __init__(self, config_name: str, checkpoint_dir: str):
        self._model = _ModelState()
        ctx = mp.get_context("spawn")
        self._parent_conn, child_conn = ctx.Pipe()
        self._process = ctx.Process(
            target=_policy_worker,
            args=(child_conn, config_name, str(checkpoint_dir)),
            daemon=True,
        )
        self._process.start()
        status, payload = self._parent_conn.recv()
        if status != "ready":
            raise RuntimeError(f"policy worker failed during startup:\n{payload}")

    def _request(self, cmd: str, payload: Any = None) -> Any:
        if not self._process.is_alive():
            raise RuntimeError("policy worker exited unexpectedly")
        self._parent_conn.send((cmd, payload))
        status, response = self._parent_conn.recv()
        if status != "ok":
            raise RuntimeError(f"policy worker failed during {cmd}:\n{response}")
        return response

    def reset(self):
        self._request("reset")
        self._model.last_uncertainty_logvar = None

    def infer(self, observation):
        response = self._request("infer", observation)
        logvar = response.get("logvar")
        self._model.last_uncertainty_logvar = _ArrayWithNumpy(logvar) if logvar is not None else None
        return response["output"]

    def close(self):
        if getattr(self, "_process", None) is None:
            return
        if self._process.is_alive():
            try:
                self._request("close")
            except Exception:
                self._process.terminate()
            self._process.join(timeout=5)


@dataclasses.dataclass(frozen=True)
class EvalTask:
    task_id_1based: int
    task_dir_name: str
    language: str
    bddl_path: pathlib.Path
    initial_states: Any
    max_steps: int
    source_suite: str
    source_task_id_1based: int
    engine_language: str = ""
    generated_task_id: str = ""
    generated_split: str = ""
    generated_template: str = ""
    generated_metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


def _get_libero_env(task: EvalTask, resolution: int, seed: int):
    from libero.libero.envs import OffScreenRenderEnv

    task_description = task.language
    env = OffScreenRenderEnv(
        bddl_file_name=str(task.bddl_path),
        camera_heights=resolution,
        camera_widths=resolution,
    )
    env.seed(seed)
    return env, task_description


def bddl_language(bddl_path: str | pathlib.Path) -> str:
    """The task language as written in the BDDL `(:language ...)` section."""

    try:
        from experiments.robot.libero.tiptop_repro.bddl_goals import parse_bddl_task_goals

        text = pathlib.Path(bddl_path).read_text(encoding="utf-8", errors="replace")
        return str((parse_bddl_task_goals(text) or {}).get("language") or "").strip()
    except Exception:
        return ""


def resolve_language_source_defaults(
    task_suite_name: str,
    task_language_source: str | None = "auto",
    engine_language_source: str | None = "auto",
) -> tuple[str, str]:
    """Resolve language-source defaults for a suite.

    LIBERO-Pro's `*_task` perturbation rewrites `(:language ...)` without changing the
    BDDL filename. Those suites must feed the BDDL language to both the policy and the
    recovery engine; other suites keep the historical filename/policy protocol.
    """

    suite = str(task_suite_name or "")
    task_source = str(task_language_source or "auto")
    engine_source = str(engine_language_source or "auto")
    is_task_axis = suite.endswith("_task")
    if task_source == "auto":
        task_source = "bddl" if is_task_axis else "filename"
    if engine_source == "auto":
        engine_source = "bddl" if is_task_axis else "policy"
    return task_source, engine_source


def apply_language_sources(tasks: list[EvalTask], args: argparse.Namespace) -> list[EvalTask]:
    """Resolve the policy prompt and the engine task description independently.

    LIBERO builds `task.language` from the BDDL *filename*, so on LIBERO-Pro suites whose
    perturbation rewrites the language inside the file (the `*_task` axis) the instruction the
    policy receives disagrees with the goal the environment checks. `auto` resolves that case
    to BDDL/BDDL and keeps the historical filename/policy behaviour everywhere else.
    """

    policy_source, engine_source = resolve_language_source_defaults(
        str(getattr(args, "task_suite_name", "") or ""),
        str(getattr(args, "task_language_source", "auto") or "auto"),
        str(getattr(args, "engine_language_source", "auto") or "auto"),
    )
    setattr(args, "task_language_source", policy_source)
    setattr(args, "engine_language_source", engine_source)
    if policy_source == "filename" and engine_source == "policy":
        return tasks
    resolved: list[EvalTask] = []
    for task in tasks:
        from_bddl = ""
        if policy_source == "bddl" or engine_source == "bddl":
            from_bddl = bddl_language(task.bddl_path)
        policy = from_bddl if (policy_source == "bddl" and from_bddl) else task.language
        engine = (from_bddl or policy) if engine_source == "bddl" else policy
        resolved.append(dataclasses.replace(task, language=policy, engine_language=engine))
    return resolved


def _read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _selected_generated_rows(rows: list[dict[str, Any]], selected: str) -> list[dict[str, Any]]:
    if not selected.strip():
        return rows
    by_id = {str(row.get("task_id") or ""): row for row in rows}
    picked: list[dict[str, Any]] = []
    for raw in selected.split(","):
        token = raw.strip()
        if not token:
            continue
        if token in by_id:
            picked.append(by_id[token])
            continue
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(rows):
                picked.append(rows[idx])
                continue
        raise ValueError(f"unknown generated task selector {token!r}")
    return picked


def _generated_manifest_rows(args: argparse.Namespace) -> tuple[pathlib.Path, list[dict[str, Any]]]:
    root = pathlib.Path(args.generated_benchmark_dir).expanduser().resolve()
    manifest = (
        root / "manifests" / "all_tasks.jsonl"
        if args.generated_split == "all"
        else root / "manifests" / f"{args.generated_split}_tasks.jsonl"
    )
    if not manifest.exists():
        raise FileNotFoundError(f"generated benchmark manifest not found: {manifest}")
    rows = sorted(_read_jsonl(manifest), key=lambda row: str(row.get("task_id") or ""))
    return root, _selected_generated_rows(rows, args.generated_task_ids)


def _libero_pro_suite_names(benchmark_dict: dict[str, Any]) -> list[str]:
    return [
        suite_name
        for suite_name in sorted(benchmark_dict)
        if suite_name.startswith("libero_") and suite_name not in LIBERO_PRO_EXCLUDED_SUITES
    ]


def _libero_task_paths(task: Any, bddl_root: pathlib.Path, init_root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    return (
        bddl_root / task.problem_folder / task.bddl_file,
        init_root / task.problem_folder / task.init_states_file,
    )


def _require_libero_task_resources(task: Any, bddl_path: pathlib.Path, init_path: pathlib.Path) -> None:
    missing = []
    if not bddl_path.exists():
        missing.append(str(bddl_path))
    if not init_path.exists():
        missing.append(str(init_path))
    if missing:
        raise FileNotFoundError(
            "LIBERO task resources are incomplete for "
            f"{getattr(task, 'name', '<unknown task>')}: {missing}"
        )


def _load_libero_pro_umbrella_tasks(args: argparse.Namespace, benchmark_module) -> list[EvalTask]:
    from libero.libero import get_libero_path

    benchmark_dict = benchmark_module.get_benchmark_dict()
    bddl_root = pathlib.Path(get_libero_path("bddl_files"))
    init_root = pathlib.Path(get_libero_path("init_states"))
    selected = (
        {int(x.strip()) for x in args.task_ids.split(",") if x.strip()}
        if args.task_ids.strip()
        else None
    )
    tasks: list[EvalTask] = []
    global_tid1 = 0
    skipped_missing = 0
    for suite_name in _libero_pro_suite_names(benchmark_dict):
        task_suite = benchmark_dict[suite_name]()
        if task_suite.n_tasks <= 0:
            continue
        for suite_task_idx in range(task_suite.n_tasks):
            task = task_suite.get_task(suite_task_idx)
            bddl_path, init_path = _libero_task_paths(task, bddl_root, init_root)
            if not bddl_path.exists() or not init_path.exists():
                skipped_missing += 1
                continue
            global_tid1 += 1
            if selected is not None and global_tid1 not in selected:
                continue
            tasks.append(
                EvalTask(
                    task_id_1based=global_tid1,
                    task_dir_name=f"{suite_name}_task{suite_task_idx + 1:02d}",
                    language=str(task.language),
                    bddl_path=bddl_path,
                    initial_states=task_suite.get_task_init_states(suite_task_idx),
                    max_steps=max_steps_for_suite(suite_name),
                    source_suite=suite_name,
                    source_task_id_1based=suite_task_idx + 1,
                )
            )
    if skipped_missing:
        print(f"[warning] skipped {skipped_missing} LIBERO-Pro tasks with missing BDDL/init resources", flush=True)
    if not tasks:
        raise ValueError("libero_pro umbrella selection produced no tasks")
    return tasks


def _load_eval_tasks(args: argparse.Namespace, benchmark_module) -> list[EvalTask]:
    from libero.libero import get_libero_path

    if not args.generated_benchmark_dir:
        if args.task_suite_name == LIBERO_PRO_UMBRELLA:
            return _load_libero_pro_umbrella_tasks(args, benchmark_module)
        task_suite = benchmark_module.get_benchmark_dict()[args.task_suite_name]()
        task_ids = (
            [int(x.strip()) for x in args.task_ids.split(",") if x.strip()]
            if args.task_ids.strip()
            else list(range(1, task_suite.n_tasks + 1))
        )
        bddl_root = pathlib.Path(get_libero_path("bddl_files"))
        init_root = pathlib.Path(get_libero_path("init_states"))
        tasks: list[EvalTask] = []
        for tid1 in task_ids:
            task = task_suite.get_task(tid1 - 1)
            bddl_path, init_path = _libero_task_paths(task, bddl_root, init_root)
            _require_libero_task_resources(task, bddl_path, init_path)
            tasks.append(
                EvalTask(
                    task_id_1based=tid1,
                    task_dir_name=f"task{tid1:02d}",
                    language=str(task.language),
                    bddl_path=bddl_path,
                    initial_states=task_suite.get_task_init_states(tid1 - 1),
                    max_steps=max_steps_for_suite(args.task_suite_name),
                    source_suite=args.task_suite_name,
                    source_task_id_1based=tid1,
                )
            )
        return tasks

    root, rows = _generated_manifest_rows(args)
    source_suites: dict[str, Any] = {}
    tasks: list[EvalTask] = []
    for row_idx, row in enumerate(rows, start=1):
        source_suite_name = str(row.get("source_suite") or args.task_suite_name)
        if source_suite_name not in source_suites:
            source_suites[source_suite_name] = benchmark_module.get_benchmark_dict()[source_suite_name]()
        source_suite = source_suites[source_suite_name]
        source_tid1 = int(row["source_task_id_1based"])
        task_id = str(row.get("task_id") or f"generated_{row_idx:04d}")
        tasks.append(
            EvalTask(
                task_id_1based=row_idx,
                task_dir_name=task_id,
                language=str(row.get("language") or ""),
                bddl_path=root / str(row["bddl_path"]),
                initial_states=source_suite.get_task_init_states(source_tid1 - 1),
                max_steps=max_steps_for_suite(source_suite_name),
                source_suite=source_suite_name,
                source_task_id_1based=source_tid1,
                generated_task_id=task_id,
                generated_split=str(row.get("split") or args.generated_split),
                generated_template=str(row.get("template") or ""),
                generated_metadata=dict(row),
            )
        )
    if not tasks:
        raise ValueError("generated benchmark selection produced no tasks")
    return tasks


def _check_task_success(env, fallback_done: bool = False) -> bool:
    check = getattr(env, "check_success", None)
    if callable(check):
        try:
            return bool(check())
        except Exception:
            pass
    return bool(fallback_done)


def _bootstrap_openvla(repo_root: str) -> None:
    root = pathlib.Path(repo_root).resolve()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "experiments" / "robot" / "libero"))


def _make_controller(args, device: str):
    _bootstrap_openvla(args.openvla_repo_root)
    from experiments.robot.libero.tiptop_repro.cutamp_like import ParticleOptimizationConfig
    from experiments.robot.libero.tiptop_repro.cutamp_controller_v2 import CuTAMPV2Config, CuTAMPV2TipTopController
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackendConfig

    particle_cfg = ParticleOptimizationConfig(
        num_particles=args.num_particles,
        num_iters=args.particle_iters,
        lr=args.particle_lr,
        device=device,
    )
    table_x_min_clip = args.real_cutamp_table_x_min_clip
    table_height_override = args.real_cutamp_table_height_override
    table_z_offset = args.real_cutamp_table_z_offset
    if args.real_cutamp_table_proxy_profile == "thin_clipped_lowered":
        table_x_min_clip = 0.12 if table_x_min_clip is None else table_x_min_clip
        table_height_override = 0.02 if table_height_override is None else table_height_override
        table_z_offset = -0.04 if table_z_offset is None else table_z_offset

    cfg = CuTAMPV2Config(
        max_replans=args.max_replans,
        max_recovery_steps=args.max_recovery_steps,
        min_success_fraction=args.min_success_fraction,
        particle_cfg=particle_cfg,
        use_real_cutamp_backend=args.use_real_cutamp_backend,
        real_cutamp_require_feasible=args.real_cutamp_require_feasible,
        prefer_real_cutamp_executable_plan=args.prefer_real_cutamp_executable_plan,
        require_real_cutamp_executable_plan=args.require_real_cutamp_executable_plan,
        recovery_goal_mode=args.recovery_goal_mode,
        real_cutamp_cfg=RealCuTAMPBackendConfig(
            robot=args.real_cutamp_robot,
            grasp_dof=args.real_cutamp_grasp_dof,
            num_particles=args.real_cutamp_num_particles,
            num_opt_steps=args.real_cutamp_num_opt_steps,
            max_loop_dur=args.real_cutamp_max_loop_dur,
            curobo_plan=args.real_cutamp_curobo_plan,
            serialize_trajectories=args.real_cutamp_serialize_trajectories,
            runner_python=args.real_cutamp_runner_python,
            runner_timeout_sec=args.real_cutamp_runner_timeout_sec,
            debug_dir=args.real_cutamp_debug_dir,
            table_x_min_clip=table_x_min_clip,
            table_height_override=table_height_override,
            table_z_offset=0.0 if table_z_offset is None else table_z_offset,
            table_as_collision_obstacle=not args.real_cutamp_no_table_collision_obstacle,
            static_context_collision_mode=args.real_cutamp_static_context_collision_mode,
            dummy_obstacle_if_empty=not args.real_cutamp_no_dummy_obstacle_if_empty,
            apply_simulator_truth_initial_state=not args.real_cutamp_disable_simulator_truth_initial_state,
            initial_state_min_confidence=args.real_cutamp_initial_state_min_confidence,
            fail_on_unsupported_holding=not args.real_cutamp_allow_unsupported_holding,
            enable_initial_holding_prebinding=not args.real_cutamp_disable_initial_holding_prebinding,
            accept_optimized_plan_if_motiongen_fails=not args.require_real_cutamp_executable_plan,
        ),
    )
    return CuTAMPV2TipTopController(cfg)


def _aperture(qpos) -> float:
    import numpy as np

    return float(np.mean(np.abs(np.asarray(qpos, dtype=np.float32))))


def _logvar_gripper_first(policy, action_chunk: int) -> float | None:
    import numpy as np

    logvar = getattr(getattr(policy, "_model", None), "last_uncertainty_logvar", None)
    if logvar is None:
        return None
    arr = np.asarray(logvar.numpy(), dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[0]
    gripper = arr[:action_chunk, 6]
    return float(gripper[0])


def _nearest_pickable_to_ee(scene, target_name: str | None) -> dict[str, Any]:
    import numpy as np

    pickables = _pickable_positions(scene)
    best = None
    best_dist = None
    for name, xyz in pickables.items():
        dist = float(np.linalg.norm(np.asarray(xyz, dtype=np.float32)[:3] - scene.ee_pos[:3]))
        if best_dist is None or dist < best_dist:
            best = name
            best_dist = dist
    return {
        "nearest_pickable_name": best,
        "nearest_pickable_distance_m": best_dist,
        "nearest_pickable_is_target": (best == target_name) if best is not None and target_name else None,
    }


def _pick_target_status(
    *,
    gripper_aperture: float | None,
    target_ee_distance_m: float | None,
    nearest_pickable_distance_m: float | None,
    nearest_pickable_is_target: bool | None,
) -> str:
    if gripper_aperture is None or gripper_aperture >= 0.02:
        return "open"
    if nearest_pickable_is_target is True:
        return "target_near"
    if (
        nearest_pickable_is_target is False
        and nearest_pickable_distance_m is not None
        and nearest_pickable_distance_m <= 0.09
        and target_ee_distance_m is not None
        and target_ee_distance_m >= 0.12
    ):
        return "non_target_near"
    if target_ee_distance_m is not None and target_ee_distance_m >= 0.12:
        return "off_target_unknown"
    return "unknown"


def _pickable_positions(scene) -> dict[str, list[float]]:
    from experiments.robot.libero.tiptop_repro.affordances import is_probably_movable, object_affordances

    out: dict[str, list[float]] = {}
    for name, obj in scene.objects.items():
        affordances = set(object_affordances(name))
        if not is_probably_movable(name):
            continue
        if affordances & {"surface", "container", "articulated", "fixture", "door_link"}:
            continue
        out[name] = obj.pos[:3].astype(float).tolist()
    return out


def _task_allows_drawer_interaction(task_description: str) -> bool:
    low = str(task_description or "").lower()
    if "drawer" not in low:
        return False
    action_drawer = r"\b(?:open|close)\b[^.]*\bdrawer\b|\bdrawer\b[^.]*\b(?:open|close)\b"
    inside_drawer = r"\b(?:in|inside|into)\b[^.]*\bdrawer\b|\bdrawer\b[^.]*\b(?:in|inside|into)\b"
    return bool(re.search(action_drawer, low) or re.search(inside_drawer, low))


def _is_articulated_blocker_name(name: str) -> bool:
    low = str(name or "").lower().replace("_", " ").replace("-", " ")
    if any(token in low for token in ("cabinet top", "top side", "inner floor", "placement region")):
        return False
    if "handle" in low and not any(token in low for token in ("cabinet", "drawer", "door", "microwave")):
        return False
    return any(token in low for token in ("cabinet", "drawer", "door", "handle"))


def _has_open_cabinet_evidence(open_joint_names: list[str]) -> bool:
    for name in open_joint_names:
        low = str(name or "").lower().replace("_", " ").replace("-", " ")
        if "cabinet" in low and any(token in low for token in ("drawer", "level", "door")):
            return True
    return False


def _is_robot_gripper_contact_name(name: str | None) -> bool:
    low = str(name or "").lower().replace("_", " ").replace("-", " ")
    return any(token in low for token in ("finger", "gripper", "hand", "eef"))


def _contact_endpoint_names(contact: dict[str, Any], idx: int) -> list[str]:
    out: list[str] = []
    for key in (f"object{idx}", f"geom{idx}_body_name", f"geom{idx}_name"):
        value = contact.get(key)
        if value:
            out.append(str(value))
    return out


def _first_articulated_blocker_name(names: list[str]) -> str | None:
    for name in names:
        if _is_articulated_blocker_name(name):
            return name
    return None


def _articulated_blocker_contact_summary(scene) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    contact_count = 0
    for contact in getattr(scene, "contacts", []) or []:
        try:
            distance = float(contact.get("distance", 0.0))
        except Exception:
            distance = 0.0
        if distance > ARTICULATED_BLOCKER_CONTACT_MAX_DISTANCE_M:
            continue
        names1 = _contact_endpoint_names(contact, 1)
        names2 = _contact_endpoint_names(contact, 2)
        robot1 = any(_is_robot_gripper_contact_name(name) for name in names1)
        robot2 = any(_is_robot_gripper_contact_name(name) for name in names2)
        blocker1 = _first_articulated_blocker_name(names1)
        blocker2 = _first_articulated_blocker_name(names2)
        if robot1 and blocker2:
            robot_name = next((name for name in names1 if _is_robot_gripper_contact_name(name)), names1[0] if names1 else None)
            blocker_name = blocker2
        elif robot2 and blocker1:
            robot_name = next((name for name in names2 if _is_robot_gripper_contact_name(name)), names2[0] if names2 else None)
            blocker_name = blocker1
        else:
            continue
        contact_count += 1
        if best is None or distance < float(best["distance_m"]):
            best = {
                "robot_name": robot_name,
                "blocker_name": blocker_name,
                "distance_m": distance,
            }
    return {
        "articulated_blocker_contact": best is not None,
        "articulated_blocker_contact_name": best.get("blocker_name") if best else None,
        "articulated_blocker_contact_robot_name": best.get("robot_name") if best else None,
        "articulated_blocker_contact_count": contact_count,
        "articulated_blocker_contact_min_distance_m": best.get("distance_m") if best else None,
    }


def _object_xyz(obj: Any) -> list[float] | None:
    import numpy as np

    try:
        arr = np.asarray(getattr(obj, "pos", None), dtype=np.float32).reshape(-1)
    except Exception:
        return None
    if arr.size < 3:
        return None
    return arr[:3].astype(float).tolist()


def _articulated_blocker_positions(scene) -> dict[str, list[float]]:
    from experiments.robot.libero.tiptop_repro.affordances import object_affordances

    out: dict[str, list[float]] = {}
    for name, obj in getattr(scene, "objects", {}).items():
        affordances = set(object_affordances(str(name)))
        if not (_is_articulated_blocker_name(str(name)) or affordances & {"articulated", "openable", "closeable"}):
            continue
        xyz = _object_xyz(obj)
        if xyz is not None:
            out[str(name)] = xyz
    return out


def _articulated_blocker_joint_state(scene) -> dict[str, Any]:
    joint_state_known = False
    open_names: list[str] = []
    joints = getattr(scene, "joints", {}) or {}
    for name, joint in getattr(joints, "items", lambda: [])():
        low = str(name or "").lower().replace("_", " ").replace("-", " ")
        if not any(token in low for token in ("cabinet", "drawer")):
            continue
        qpos = getattr(joint, "qpos", None)
        if qpos is None:
            continue
        try:
            value = float(qpos)
        except Exception:
            continue
        joint_state_known = True
        if abs(value) > ARTICULATED_BLOCKER_OPEN_QPOS_THRESHOLD:
            open_names.append(str(name))
    return {
        "articulated_blocker_joint_state_known": joint_state_known,
        "articulated_blocker_open_joint_names": open_names[:8],
    }


def _target_orientation_features(scene, target_name: str | None) -> dict[str, Any]:
    import numpy as np

    from experiments.robot.libero.tiptop_repro.libero_panda_frames import quat_wxyz_to_matrix

    if not target_name or target_name not in scene.objects:
        return {
            "target_quat": None,
            "target_orientation": None,
            "target_upright_axis_alignment": None,
        }
    obj = scene.objects[target_name]
    quat = np.asarray(obj.quat if obj.quat is not None else [1.0, 0.0, 0.0, 0.0], dtype=np.float64).reshape(-1)
    if quat.size < 4:
        return {
            "target_quat": None,
            "target_orientation": None,
            "target_upright_axis_alignment": None,
        }
    world_from_obj = quat_wxyz_to_matrix(quat[:4])
    # LIBERO HOPE cartons (milk/orange_juice) use local +Y as their semantic
    # upright axis. Non-carton skills may ignore this field.
    upright_axis_world = world_from_obj[:, 1]
    alignment = abs(float(upright_axis_world[2]))
    if alignment >= 0.72:
        orientation = "upright"
    elif alignment <= 0.45:
        orientation = "fallen"
    else:
        orientation = "tilted"
    return {
        "target_quat": quat[:4].astype(float).tolist(),
        "target_orientation": orientation,
        "target_upright_axis_alignment": alignment,
    }


def _future_ee_xy_path(current_xyz: list[float], action_chunk: Any, action_chunk_len: int) -> list[list[float]]:
    import numpy as np

    current = np.asarray(current_xyz[:3], dtype=np.float32)
    actions = np.asarray(action_chunk, dtype=np.float32)
    if actions.ndim != 2 or actions.shape[1] < 3:
        return [current[:2].astype(float).tolist()]
    xyz_delta = actions[: max(1, int(action_chunk_len)), :3]
    if xyz_delta.size == 0:
        return [current[:2].astype(float).tolist()]
    cumulative = np.cumsum(xyz_delta, axis=0)
    final_norm = float(np.linalg.norm(cumulative[-1]))
    if final_norm > 0.16:
        cumulative = cumulative * (0.16 / final_norm)
    elif final_norm < 1e-4:
        cumulative = np.zeros_like(cumulative)
    points = current[None, :3] + cumulative
    return [current[:2].astype(float).tolist()] + points[:, :2].astype(float).tolist()


def _min_xy_distance(path_xy: list[list[float]], xyz: list[float]) -> float:
    import numpy as np

    pts = np.asarray(path_xy, dtype=np.float32)
    obj = np.asarray(xyz[:2], dtype=np.float32)
    return float(np.min(np.linalg.norm(pts - obj[None, :], axis=1)))


def _motion_since(
    positions: dict[str, list[float]],
    reference: dict[str, list[float]] | None,
    name: str | None,
) -> float | None:
    import numpy as np

    if not name or not reference or name not in positions or name not in reference:
        return None
    return float(np.linalg.norm(np.asarray(positions[name], dtype=np.float32) - np.asarray(reference[name], dtype=np.float32)))


def _suffix_count(history: collections.deque, value: str | None) -> int:
    if not value:
        return 0
    count = 0
    for item in reversed(history):
        if item != value:
            break
        count += 1
    return count


def _goal_xy_distance(qstate: dict[str, Any], xyz: list[float] | None) -> float | None:
    import numpy as np

    if not xyz:
        return None
    goal_xyz = qstate.get("goal_xyz")
    if not goal_xyz:
        return None
    try:
        obj_xy = np.asarray(xyz[:2], dtype=np.float32)
        goal_xy = np.asarray(goal_xyz[:2], dtype=np.float32)
    except Exception:
        return None
    if obj_xy.size < 2 or goal_xy.size < 2:
        return None
    return float(np.linalg.norm(obj_xy - goal_xy))


def _wrong_object_progress_features(
    *,
    qstate: dict[str, Any],
    previous_positions: dict[str, list[float]] | None,
    baseline_positions: dict[str, list[float]] | None,
) -> dict[str, Any]:
    import numpy as np

    positions = dict(qstate.get("pickable_positions") or {})
    target_name = qstate.get("target_name")
    target_total_motion = _motion_since(positions, baseline_positions, target_name)
    target_static = target_total_motion is not None and target_total_motion <= 0.015

    best_name = None
    best_total_motion = None
    best_step_motion = None
    for name in positions:
        if target_name and name == target_name:
            continue
        total_motion = _motion_since(positions, baseline_positions, name)
        if total_motion is None:
            continue
        if best_total_motion is None or total_motion > best_total_motion:
            best_name = name
            best_total_motion = float(total_motion)
            best_step_motion = _motion_since(positions, previous_positions, name)

    best_xyz = positions.get(best_name) if best_name else None
    goal_xy_distance = _goal_xy_distance(qstate, best_xyz)
    intent_name = qstate.get("intent_object_name")
    is_intent = bool(best_name and intent_name and best_name == intent_name and qstate.get("intent_object_is_target") is False)
    holding_object = qstate.get("holding_object")
    is_held = bool(best_name and holding_object and best_name == holding_object)
    near_ee = None
    if best_xyz and qstate.get("ee_xyz"):
        try:
            near_ee = float(
                np.linalg.norm(
                    np.asarray(best_xyz[:3], dtype=np.float32) - np.asarray(qstate["ee_xyz"][:3], dtype=np.float32)
                )
            )
        except Exception:
            near_ee = None

    status = "no_wrong_progress"
    if best_name and target_static and best_total_motion is not None:
        if best_total_motion >= 0.06 and goal_xy_distance is not None and goal_xy_distance <= 0.18:
            status = "wrong_object_at_goal"
        elif best_total_motion >= 0.12 and (is_intent or is_held or (near_ee is not None and near_ee <= 0.12)):
            status = "wrong_object_transported"

    return {
        "wrong_progress_object_name": best_name,
        "wrong_progress_object_total_motion_m": best_total_motion,
        "wrong_progress_object_step_motion_m": best_step_motion,
        "wrong_progress_object_goal_xy_distance_m": goal_xy_distance,
        "wrong_progress_object_ee_distance_m": near_ee,
        "wrong_progress_object_is_intent": is_intent,
        "wrong_progress_object_is_held": is_held,
        "wrong_progress_target_static": target_static,
        "vla_wrong_object_progress_status": status,
    }


def _suffix_true_count(history: collections.deque) -> int:
    count = 0
    for item in reversed(history):
        if not bool(item):
            break
        count += 1
    return count


def _trajectory_intent_features(
    *,
    qstate: dict[str, Any],
    action_chunk: Any,
    action_chunk_len: int,
    previous_positions: dict[str, list[float]] | None,
    baseline_positions: dict[str, list[float]] | None,
    intent_history: collections.deque,
) -> dict[str, Any]:
    positions = dict(qstate.get("pickable_positions") or {})
    target_name = qstate.get("target_name")
    path_xy = _future_ee_xy_path(qstate["ee_xyz"], action_chunk, action_chunk_len)
    distances = {name: _min_xy_distance(path_xy, xyz) for name, xyz in positions.items()}
    intent_name = min(distances, key=distances.get) if distances else None
    intent_min = distances.get(intent_name) if intent_name else None
    target_future_min = distances.get(target_name) if target_name else None
    best_non_target_name = None
    best_non_target_min = None
    for name, dist in distances.items():
        if target_name and name == target_name:
            continue
        if best_non_target_min is None or dist < best_non_target_min:
            best_non_target_name = name
            best_non_target_min = dist
    if best_non_target_name is not None and (
        intent_name is None or best_non_target_min is not None and best_non_target_min < float(intent_min)
    ):
        intent_name = best_non_target_name
        intent_min = best_non_target_min
    intent_is_target = (intent_name == target_name) if intent_name and target_name else None
    margin = None
    if best_non_target_min is not None and target_future_min is not None:
        margin = float(target_future_min - best_non_target_min)

    candidate = intent_name if intent_is_target is False and intent_min is not None and intent_min <= 0.09 else ""
    intent_history.append(candidate)
    persist = _suffix_count(intent_history, candidate)

    intent_motion = _motion_since(positions, previous_positions, intent_name)
    intent_total_motion = _motion_since(positions, baseline_positions, intent_name)
    target_motion = _motion_since(positions, previous_positions, target_name)
    target_total_motion = _motion_since(positions, baseline_positions, target_name)

    target_still = target_total_motion is None or target_total_motion <= 0.015
    trajectory_base = bool(
        intent_is_target is False
        and intent_min is not None
        and intent_min <= 0.075
        and target_future_min is not None
        and target_future_min >= 0.10
        and margin is not None
        and margin >= 0.035
        and target_still
    )
    motion_boost = bool(trajectory_base and intent_total_motion is not None and intent_total_motion >= 0.015)

    status = qstate.get("vla_pick_target_status")
    if motion_boost:
        status = "non_target_intent_with_motion"
    elif trajectory_base and persist >= 2:
        status = "non_target_intent"

    return {
        "intent_object_name": intent_name,
        "intent_object_is_target": intent_is_target,
        "intent_min_xy_distance_m": intent_min,
        "target_future_min_xy_distance_m": target_future_min,
        "wrong_object_intent_margin_m": margin,
        "wrong_object_intent_persist_queries": persist,
        "intent_object_motion_m": intent_motion,
        "intent_object_total_motion_m": intent_total_motion,
        "target_motion_m": target_motion,
        "target_total_motion_m": target_total_motion,
        "vla_pick_target_status": status,
    }


def _articulated_blocker_features(
    *,
    qstate: dict[str, Any],
    action_chunk: Any,
    action_chunk_len: int,
    task_description: str,
    contact_history: collections.deque | None = None,
) -> dict[str, Any]:
    import numpy as np

    features: dict[str, Any] = {
        "nearest_articulated_blocker_name": None,
        "nearest_articulated_blocker_distance_m": None,
        "path_articulated_blocker_name": None,
        "path_articulated_blocker_min_xy_distance_m": None,
        "blocker_target_future_min_xy_distance_m": None,
        "articulated_blocker_contact": bool(qstate.get("articulated_blocker_contact")),
        "articulated_blocker_contact_name": qstate.get("articulated_blocker_contact_name"),
        "articulated_blocker_contact_robot_name": qstate.get("articulated_blocker_contact_robot_name"),
        "articulated_blocker_contact_count": qstate.get("articulated_blocker_contact_count"),
        "articulated_blocker_contact_min_distance_m": qstate.get("articulated_blocker_contact_min_distance_m"),
        "articulated_blocker_contact_persist_queries": 0,
        "vla_articulated_blocker_status": "unknown",
    }
    blockers = dict(qstate.get("articulated_blocker_positions") or {})
    features["articulated_blocker_joint_state_known"] = bool(
        qstate.get("articulated_blocker_joint_state_known")
    )
    features["articulated_blocker_open_joint_names"] = list(
        qstate.get("articulated_blocker_open_joint_names") or []
    )

    ee_xyz = qstate.get("ee_xyz")
    if isinstance(ee_xyz, (list, tuple)) and len(ee_xyz) >= 3 and blockers:
        ee = np.asarray(ee_xyz[:3], dtype=np.float32)
        nearest_name = None
        nearest_dist = None
        for name, xyz in blockers.items():
            dist = float(np.linalg.norm(np.asarray(xyz, dtype=np.float32)[:3] - ee))
            if nearest_dist is None or dist < nearest_dist:
                nearest_name = name
                nearest_dist = dist
        features["nearest_articulated_blocker_name"] = nearest_name
        features["nearest_articulated_blocker_distance_m"] = nearest_dist

    path_xy = _future_ee_xy_path(qstate["ee_xyz"], action_chunk, action_chunk_len)
    target_xyz = qstate.get("target_xyz")
    if isinstance(target_xyz, (list, tuple)) and len(target_xyz) >= 3:
        features["blocker_target_future_min_xy_distance_m"] = _min_xy_distance(path_xy, list(target_xyz))
    if blockers:
        path_dists = {name: _min_xy_distance(path_xy, xyz) for name, xyz in blockers.items()}
        path_name = min(path_dists, key=path_dists.get)
        features["path_articulated_blocker_name"] = path_name
        features["path_articulated_blocker_min_xy_distance_m"] = path_dists[path_name]

    target_name = str(qstate.get("target_name") or "").lower()
    aperture = qstate.get("gripper_aperture")
    target_ee = qstate.get("target_ee_distance_m")
    holding_status = str(qstate.get("holding_status") or "")
    open_joint_names = list(features["articulated_blocker_open_joint_names"] or [])
    has_open_cabinet = _has_open_cabinet_evidence(open_joint_names)
    has_cabinet_blocker = any("cabinet" in str(name).lower() for name in blockers)
    target_far = target_ee is not None and float(target_ee) > OPEN_CABINET_BOWL_PICK_TARGET_FAR_M
    contact_active = bool(features["articulated_blocker_contact"] and has_open_cabinet and has_cabinet_blocker)
    if contact_history is not None:
        contact_history.append(contact_active)
        contact_persist = _suffix_true_count(contact_history)
    else:
        contact_persist = 1 if contact_active else 0
    features["articulated_blocker_contact_persist_queries"] = contact_persist

    if "bowl" not in target_name:
        status = "not_bowl_target"
    elif _task_allows_drawer_interaction(task_description):
        status = "task_allows_drawer_interaction"
    elif aperture is None or float(aperture) <= 0.025:
        status = "not_open_hand"
    elif holding_status != "handempty_or_unconfirmed":
        status = "not_empty_hand"
    elif not target_far:
        status = "target_near"
    elif not blockers:
        status = "no_articulated_blocker"
    elif not open_joint_names:
        status = "drawer_not_open"
    else:
        status = (
            "blocked_open_drawer_before_pick"
            if contact_persist >= ARTICULATED_BLOCKER_CONTACT_TRIGGER_QUERIES
            else "clear"
        )
    features["vla_articulated_blocker_status"] = status
    return features


def _query_state(env, obs, task_description: str) -> dict[str, Any]:
    import numpy as np

    from experiments.robot.libero.tiptop_repro.scene_reader import read_scene
    from experiments.robot.libero.tiptop_repro.task_parser import parse_task

    scene = read_scene(env, obs)
    parsed = parse_task(task_description, scene.objects.keys(), env=env)
    diagnostics = dict(parsed.diagnostics or {})
    target_name = parsed.target_hint
    goal_name = parsed.goal_hint
    target_xyz = None
    target_ee_distance_m = None
    if target_name and target_name in scene.objects:
        target_xyz = scene.objects[target_name].pos[:3].astype(float).tolist()
        target_ee_distance_m = float(np.linalg.norm(scene.objects[target_name].pos[:3] - scene.ee_pos[:3]))
    goal_xyz = None
    if goal_name and goal_name in scene.objects:
        goal_xyz = scene.objects[goal_name].pos[:3].astype(float).tolist()
    holding = compact_holding(scene, target_name)
    nearest_pickable = _nearest_pickable_to_ee(scene, target_name)
    pickable_positions = _pickable_positions(scene)
    articulated_blocker_positions = _articulated_blocker_positions(scene)
    articulated_joint_state = _articulated_blocker_joint_state(scene)
    articulated_blocker_contact = _articulated_blocker_contact_summary(scene)
    orientation = _target_orientation_features(scene, target_name)
    gripper_aperture = _aperture(scene.gripper_qpos)
    vla_pick_target_status = _pick_target_status(
        gripper_aperture=gripper_aperture,
        target_ee_distance_m=target_ee_distance_m,
        nearest_pickable_distance_m=nearest_pickable["nearest_pickable_distance_m"],
        nearest_pickable_is_target=nearest_pickable["nearest_pickable_is_target"],
    )
    return {
        "ee_xyz": scene.ee_pos[:3].astype(float).tolist(),
        "ee_quat": scene.ee_quat[:4].astype(float).tolist(),
        "gripper_qpos": scene.gripper_qpos.astype(float).tolist(),
        "gripper_aperture": gripper_aperture,
        "target_name": target_name,
        "target_xyz": target_xyz,
        **orientation,
        "target_ee_distance_m": target_ee_distance_m,
        "goal_name": goal_name,
        "goal_xyz": goal_xyz,
        "bddl_goal_surfaces": diagnostics.get("bddl_goal_surfaces") or [],
        "bddl_goal_atoms": diagnostics.get("bddl_goal_atoms") or [],
        "bddl_regions": diagnostics.get("bddl_regions") or {},
        **nearest_pickable,
        "vla_pick_target_status": vla_pick_target_status,
        "pickable_positions": pickable_positions,
        "articulated_blocker_positions": articulated_blocker_positions,
        **articulated_joint_state,
        **articulated_blocker_contact,
        **holding,
    }


def _setup_logger(exp_name: str, log_dir: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(log_dir, f"{exp_name}.log"), mode="w"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    return logging.getLogger("skill_pipeline.runner")


def main(args: argparse.Namespace | None = None) -> None:
    if args is None:
        args = parse_args()
    check_trigger_exclusivity(args)

    os.environ.setdefault("MUJOCO_GL", "egl")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    _patch_torch_load()

    import numpy as np
    from libero.libero import benchmark

    logger = _setup_logger(args.exp_name, args.log_dir)
    np.random.seed(args.seed)
    eval_tasks = apply_language_sources(_load_eval_tasks(args, benchmark), args)

    logger.info("policy setup start")
    if args.policy_in_process:
        _patch_torch_load()
        policy = JaxOpenPIUncertaintyPolicyAdapter(args.config_name, args.pretrained_path)
    else:
        policy = SubprocessOpenPIUncertaintyPolicyAdapter(args.config_name, args.pretrained_path)
    logger.info("policy setup done")

    out_dir = pathlib.Path(args.log_dir) / args.exp_name
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.real_cutamp_debug_dir:
        args.real_cutamp_debug_dir = str(out_dir / "cutamp_debug")
    pathlib.Path(args.real_cutamp_debug_dir).mkdir(parents=True, exist_ok=True)

    skill_config = resolve_skill_config(
        skill_pack=args.skill_pack or None,
        skill_index=args.skill_index or None,
        capability_registry=args.capability_registry or None,
        diagnostic_signal_registry=args.diagnostic_signal_registry or None,
        predicate_registry=args.predicate_registry or None,
        predicate_adapter=args.predicate_adapter or None,
        default_index=default_skills_index(),
        default_diagnostic_registry_path=default_diagnostic_signal_registry(),
    )
    skill_config_summary = skill_config.to_summary()

    runtime_factory = None
    capability_registry_summary: dict[str, Any] = {}
    if args.enable_skills or args.enable_mining_skills:
        from .capabilities import load_capability_registry
        from .geometry_profiles import load_geometry_profile_registry
        from .grounding_profiles import load_grounding_profile_registry
        from .place_profiles import load_place_profile_registry
        from .predicate_registry import load_predicate_registry
        from .repair_profiles import load_repair_profile_registry
        from .runtime import SkillRuntime
        from .schema import resolve_mining_skills
        from experiments.robot.libero.tiptop_repro.grasp_profiles import load_grasp_profile_registry

        capability_registry = load_capability_registry(
            skill_config.capability_registry,
            index_path=skill_config.skill_index,
        )
        repair_profile_registry = load_repair_profile_registry(
            skill_config.repair_profile_registry,
            index_path=skill_config.skill_index,
        )
        place_profile_registry = load_place_profile_registry(
            skill_config.place_profile_registry,
            adapter_path=skill_config.place_policy_adapter,
            index_path=skill_config.skill_index,
        )
        grasp_profile_registry = load_grasp_profile_registry(
            skill_config.grasp_profile_adapter,
            index_path=skill_config.skill_index,
        )
        grounding_profile_registry = load_grounding_profile_registry(
            skill_config.grounding_profile_registry,
            adapter_path=skill_config.grounding_profile_adapter,
            index_path=skill_config.skill_index,
        )
        geometry_profile_registry = load_geometry_profile_registry(
            skill_config.geometry_profile_registry,
            adapter_path=skill_config.geometry_profile_adapter,
            index_path=skill_config.skill_index,
        )
        predicate_registry = load_predicate_registry(
            skill_config.predicate_registry,
            adapter_path=skill_config.predicate_adapter,
            index_path=skill_config.skill_index,
        )
        capability_registry_summary = capability_registry.summary()
        if skill_config.skill_pack is not None:
            logger.info("skill pack: %s root=%s", skill_config.skill_pack.name, skill_config.skill_pack.root)
        logger.info("loading skills from %s", skill_config.skill_index)
        if capability_registry.enabled:
            logger.info(
                "skill capability registry: %s strict=%s path=%s",
                capability_registry.name,
                capability_registry.strict,
                capability_registry.path,
            )
        if repair_profile_registry.enabled:
            logger.info(
                "repair profile registry: %s path=%s profiles=%s",
                repair_profile_registry.name,
                repair_profile_registry.path,
                sorted(repair_profile_registry.profiles),
            )
        if place_profile_registry.enabled:
            logger.info(
                "place profile registry: %s path=%s profiles=%s adapters=%s",
                place_profile_registry.name,
                place_profile_registry.path,
                sorted(place_profile_registry.profiles),
                [adapter.name for adapter in place_profile_registry.adapters],
            )
        if grasp_profile_registry.enabled:
            logger.info(
                "grasp profile adapter registry: %s profiles=%s",
                grasp_profile_registry.name,
                sorted(grasp_profile_registry.profile_ids),
            )
        if grounding_profile_registry.enabled:
            logger.info(
                "grounding profile registry: %s path=%s profiles=%s adapters=%s",
                grounding_profile_registry.name,
                grounding_profile_registry.path,
                sorted(grounding_profile_registry.profiles),
                [adapter.name for adapter in grounding_profile_registry.adapters],
            )
        if geometry_profile_registry.enabled:
            logger.info(
                "geometry profile registry: %s path=%s profiles=%s adapters=%s",
                geometry_profile_registry.name,
                geometry_profile_registry.path,
                sorted(geometry_profile_registry.profiles),
                [adapter.name for adapter in geometry_profile_registry.adapters],
            )
        if predicate_registry.enabled:
            logger.info(
                "predicate registry: %s path=%s predicates=%s applies=%s adapters=%s",
                predicate_registry.name,
                predicate_registry.path,
                sorted(predicate_registry.predicates),
                sorted(predicate_registry.applies_predicates),
                [adapter.name for adapter in predicate_registry.adapters],
            )
        if args.enable_mining_skills:
            loaded_skills = resolve_mining_skills(skill_config.skill_index, predicate_registry=predicate_registry)
            logger.info("mining skills (fail_only+pair): %s", [skill.id for skill in loaded_skills])
        else:
            loaded = SkillRuntime.from_index(
                skill_config.skill_index,
                capability_registry=capability_registry,
                repair_profile_registry=repair_profile_registry,
                place_profile_registry=place_profile_registry,
                grasp_profile_registry=grasp_profile_registry,
                grounding_profile_registry=grounding_profile_registry,
                geometry_profile_registry=geometry_profile_registry,
                predicate_registry=predicate_registry,
            )
            loaded_skills = list(loaded.skills)
            logger.info("online skills: %s", [skill.id for skill in loaded_skills])

        def runtime_factory():
            return SkillRuntime(
                list(loaded_skills),
                capability_registry=capability_registry,
                repair_profile_registry=repair_profile_registry,
                place_profile_registry=place_profile_registry,
                grasp_profile_registry=grasp_profile_registry,
                grounding_profile_registry=grounding_profile_registry,
                geometry_profile_registry=geometry_profile_registry,
                predicate_registry=predicate_registry,
            )

    diagnostic_signal_factory = None
    if args.diagnostic_signal_statuses.strip():
        from .diagnostics.registry import load_registry
        from .diagnostics.runtime import DiagnosticSignalRuntime, parse_active_statuses

        active_statuses = parse_active_statuses(args.diagnostic_signal_statuses)
        registry_path = skill_config.diagnostic_signal_registry
        provider_roots = []
        if skill_config.skill_pack is not None:
            provider_roots.append(skill_config.skill_pack.root)
        diagnostic_registry = load_registry(registry_path, provider_roots=provider_roots)
        active_specs = diagnostic_registry.for_statuses(active_statuses)
        logger.info(
            "diagnostic signals enabled statuses=%s specs=%s registry=%s",
            sorted(active_statuses),
            [spec.id for spec in active_specs],
            registry_path,
        )

        def diagnostic_signal_factory():
            return DiagnosticSignalRuntime.from_registry(diagnostic_registry, active_statuses=active_statuses)

    device = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES", "") else "cpu"
    total_episodes = 0
    total_successes = 0
    early_stops: list[dict[str, Any]] = []

    for eval_task in eval_tasks:
        task_id = eval_task.source_task_id_1based - 1
        tid1 = eval_task.task_id_1based
        initial_states = eval_task.initial_states
        env, task_description = _get_libero_env(eval_task, LIBERO_ENV_RESOLUTION, args.seed)
        # `task_description` is the policy prompt; the engine plans against `engine_description`,
        # which differs from it when the suite's instruction and the checked goal disagree.
        engine_description = eval_task.engine_language or task_description
        task_dir = out_dir / eval_task.task_dir_name
        max_steps = eval_task.max_steps
        n_episodes = args.num_trials_per_task
        if not int(getattr(args, "episode_seed_start", 0) or 0):
            n_episodes = min(args.num_trials_per_task, len(initial_states))
        task_completed_episodes = 0
        task_successes = 0
        episode_start = int(getattr(args, "episode_index_start", 0))
        for episode_idx in range(episode_start, episode_start + n_episodes):
            episode_seed = episode_seed_for_index(args.seed, episode_idx, args.episode_seed_start)
            init_state_idx = init_state_index_for_episode(episode_idx, len(initial_states))
            logger.info(
                "Task %s episode %d seed %d init_state_idx %d",
                task_description,
                episode_idx,
                episode_seed,
                init_state_idx,
            )
            controller = None
            policy.reset()
            env.seed(episode_seed)
            env.reset()
            obs = env.set_init_state(initial_states[init_state_idx])
            writer = EpisodeWriter(task_dir / f"ep{episode_idx:02d}")
            runtime = runtime_factory() if runtime_factory is not None else None
            diagnostic_signal_runtime = diagnostic_signal_factory() if diagnostic_signal_factory is not None else None
            action_plan: collections.deque = collections.deque()
            done = False
            query_idx = 0
            recovery_calls = 0
            episode_abort = False
            episode_abort_reason = ""
            video_frames: list[Any] = []
            last_t = 0
            baseline_pickable_positions: dict[str, list[float]] | None = None
            previous_pickable_positions: dict[str, list[float]] | None = None
            wrong_object_intent_history: collections.deque = collections.deque(maxlen=4)
            articulated_blocker_contact_history: collections.deque = collections.deque(
                maxlen=ARTICULATED_BLOCKER_CONTACT_TRIGGER_QUERIES
            )

            for t in range(max_steps + args.num_steps_wait):
                last_t = t
                if t < args.num_steps_wait:
                    obs, _, done, _ = env.step(LIBERO_DUMMY_ACTION)
                    continue
                img = np.ascontiguousarray(obs["agentview_image"][::-1, ::-1])
                wrist_img = np.ascontiguousarray(obs["robot0_eye_in_hand_image"][::-1, ::-1])
                if args.save_video:
                    video_frames.append(img)

                if not action_plan:
                    state = np.concatenate(
                        (obs["robot0_eef_pos"], _quat2axisangle(obs["robot0_eef_quat"]), obs["robot0_gripper_qpos"])
                    )
                    out = policy.infer(
                        {
                            "observation/image": img,
                            "observation/wrist_image": wrist_img,
                            "observation/state": state,
                            "prompt": str(task_description),
                        }
                    )
                    action_chunk = out["actions"]
                    qstate = _query_state(env, obs, str(engine_description))
                    pickable_positions = dict(qstate.get("pickable_positions") or {})
                    if baseline_pickable_positions is None:
                        baseline_pickable_positions = dict(pickable_positions)
                    qstate.update(
                        _trajectory_intent_features(
                            qstate=qstate,
                            action_chunk=action_chunk,
                            action_chunk_len=args.action_chunk,
                            previous_positions=previous_pickable_positions,
                            baseline_positions=baseline_pickable_positions,
                            intent_history=wrong_object_intent_history,
                        )
                    )
                    qstate.update(
                        _wrong_object_progress_features(
                            qstate=qstate,
                            previous_positions=previous_pickable_positions,
                            baseline_positions=baseline_pickable_positions,
                        )
                    )
                    qstate.update(
                        _articulated_blocker_features(
                            qstate=qstate,
                            action_chunk=action_chunk,
                            action_chunk_len=args.action_chunk,
                            task_description=str(engine_description),
                            contact_history=articulated_blocker_contact_history,
                        )
                    )
                    previous_pickable_positions = dict(pickable_positions)
                    gripper_cmd = float(np.asarray(action_chunk)[0, 6])
                    hook_decision = None
                    hook_state = {
                        **qstate,
                        "label": "",
                        "aperture": qstate["gripper_aperture"],
                        "task_description": str(engine_description),
                    }
                    diagnostic_signals = (
                        diagnostic_signal_runtime.compute("after_pi0_query", hook_state)
                        if diagnostic_signal_runtime is not None
                        else {}
                    )
                    hook_state["diagnostic_signals"] = diagnostic_signals
                    if runtime is not None:
                        hook_decision = runtime.after_pi0_query(hook_state)
                    enter_recovery = bool(hook_decision and hook_decision.get("enter_recovery"))
                    forced = args.force_recovery_query >= 0 and query_idx == args.force_recovery_query
                    if forced and hook_decision is None and runtime is not None:
                        hook_decision = runtime.force_recovery_query(hook_state)
                    if forced:
                        enter_recovery = True
                    will_recover = bool(enter_recovery and recovery_calls < args.max_recovery_calls)
                    recovery_hints = dict((hook_decision or {}).get("recovery_hints") or {})
                    skill_match_diagnostics = (
                        list(getattr(runtime, "last_hook_diagnostics", []) or []) if runtime is not None else []
                    )
                    mode = "recovery" if will_recover else "vla"
                    record = make_query_record(
                        {
                            "task_id_1based": tid1,
                            "episode_idx": episode_idx,
                            "seed": episode_seed,
                            "query_idx": query_idx,
                            "env_step": t,
                            "mode": mode,
                            "ee_xyz": qstate["ee_xyz"],
                            "ee_quat": qstate["ee_quat"],
                            "gripper_qpos": qstate["gripper_qpos"],
                            "gripper_aperture": qstate["gripper_aperture"],
                            "gripper_cmd": gripper_cmd,
                            "target_name": qstate["target_name"],
                            "target_xyz": qstate["target_xyz"],
                            "target_quat": qstate["target_quat"],
                            "target_orientation": qstate["target_orientation"],
                            "target_upright_axis_alignment": qstate["target_upright_axis_alignment"],
                            "target_ee_distance_m": qstate["target_ee_distance_m"],
                            "goal_name": qstate["goal_name"],
                            "goal_xyz": qstate["goal_xyz"],
                            "bddl_goal_surfaces": qstate["bddl_goal_surfaces"],
                            "bddl_goal_atoms": qstate["bddl_goal_atoms"],
                            "bddl_regions": qstate["bddl_regions"],
                            "nearest_pickable_name": qstate["nearest_pickable_name"],
                            "nearest_pickable_distance_m": qstate["nearest_pickable_distance_m"],
                            "nearest_pickable_is_target": qstate["nearest_pickable_is_target"],
                            "vla_pick_target_status": qstate["vla_pick_target_status"],
                            "intent_object_name": qstate["intent_object_name"],
                            "intent_object_is_target": qstate["intent_object_is_target"],
                            "intent_min_xy_distance_m": qstate["intent_min_xy_distance_m"],
                            "target_future_min_xy_distance_m": qstate["target_future_min_xy_distance_m"],
                            "wrong_object_intent_margin_m": qstate["wrong_object_intent_margin_m"],
                            "wrong_object_intent_persist_queries": qstate["wrong_object_intent_persist_queries"],
                            "intent_object_motion_m": qstate["intent_object_motion_m"],
                            "intent_object_total_motion_m": qstate["intent_object_total_motion_m"],
                            "target_motion_m": qstate["target_motion_m"],
                            "target_total_motion_m": qstate["target_total_motion_m"],
                            "wrong_progress_object_name": qstate["wrong_progress_object_name"],
                            "wrong_progress_object_total_motion_m": qstate["wrong_progress_object_total_motion_m"],
                            "wrong_progress_object_step_motion_m": qstate["wrong_progress_object_step_motion_m"],
                            "wrong_progress_object_goal_xy_distance_m": qstate[
                                "wrong_progress_object_goal_xy_distance_m"
                            ],
                            "wrong_progress_object_ee_distance_m": qstate["wrong_progress_object_ee_distance_m"],
                            "wrong_progress_object_is_intent": qstate["wrong_progress_object_is_intent"],
                            "wrong_progress_object_is_held": qstate["wrong_progress_object_is_held"],
                            "wrong_progress_target_static": qstate["wrong_progress_target_static"],
                            "vla_wrong_object_progress_status": qstate["vla_wrong_object_progress_status"],
                            "nearest_articulated_blocker_name": qstate["nearest_articulated_blocker_name"],
                            "nearest_articulated_blocker_distance_m": qstate[
                                "nearest_articulated_blocker_distance_m"
                            ],
                            "path_articulated_blocker_name": qstate["path_articulated_blocker_name"],
                            "path_articulated_blocker_min_xy_distance_m": qstate[
                                "path_articulated_blocker_min_xy_distance_m"
                            ],
                            "blocker_target_future_min_xy_distance_m": qstate[
                                "blocker_target_future_min_xy_distance_m"
                            ],
                            "articulated_blocker_joint_state_known": qstate[
                                "articulated_blocker_joint_state_known"
                            ],
                            "articulated_blocker_open_joint_names": qstate[
                                "articulated_blocker_open_joint_names"
                            ],
                            "articulated_blocker_contact": qstate["articulated_blocker_contact"],
                            "articulated_blocker_contact_name": qstate["articulated_blocker_contact_name"],
                            "articulated_blocker_contact_robot_name": qstate[
                                "articulated_blocker_contact_robot_name"
                            ],
                            "articulated_blocker_contact_count": qstate["articulated_blocker_contact_count"],
                            "articulated_blocker_contact_min_distance_m": qstate[
                                "articulated_blocker_contact_min_distance_m"
                            ],
                            "articulated_blocker_contact_persist_queries": qstate[
                                "articulated_blocker_contact_persist_queries"
                            ],
                            "vla_articulated_blocker_status": qstate["vla_articulated_blocker_status"],
                            "holding_status": qstate["holding_status"],
                            "holding_object": qstate["holding_object"],
                            "bilateral": qstate["bilateral"],
                            "object_followed": None,
                            "logvar_gripper_first": _logvar_gripper_first(policy, args.action_chunk),
                            "residual_score": None,
                            "diagnostic_signals": diagnostic_signals,
                            "hook_fired": bool(hook_decision),
                            "skill_id": (hook_decision or {}).get("skill_id") or "",
                            "recovery_hints": recovery_hints,
                            "skill_match_diagnostics": skill_match_diagnostics,
                        }
                    )
                    writer.append_query(record)
                    writer.save_query_frame(query_idx, img)

                    if will_recover:
                        recovery_calls += 1
                        if controller is None:
                            controller = _make_controller(args, device)

                        def _record_step(step_obs: dict[str, Any], meta: dict[str, Any]) -> None:
                            if not args.save_video:
                                return
                            rec_img = np.ascontiguousarray(step_obs["agentview_image"][::-1, ::-1])
                            video_frames.append(rec_img)
                            del meta

                        result = controller.recover(
                            env,
                            obs,
                            str(engine_description),
                            step_callback=_record_step,
                            hook_bridge=runtime,
                            recovery_hints=recovery_hints,
                        )
                        obs = result.obs
                        skill_id = (hook_decision or {}).get("skill_id") or ""
                        for attempt in result.attempts:
                            rule_row = dict((attempt.planner_backend or {}).get("rule_layer") or {})
                            if rule_row:
                                rule_row.setdefault("kind", "rule")
                                rule_row["query_idx"] = query_idx
                                rule_row["skill_id"] = skill_id
                                rule_row["success"] = True
                                rule_row["error"] = ""
                                writer.append_recovery(rule_row)
                            bridge_diag = dict((attempt.planner_backend or {}).get("execution_bridge_diagnostics") or {})
                            entry_lift = bridge_diag.get("recovery_entry_lift")
                            if isinstance(entry_lift, dict):
                                writer.append_recovery(
                                    {
                                        "kind": "execution_bridge",
                                        "label": "recovery_entry_lift",
                                        "query_idx": query_idx,
                                        "skill_id": skill_id,
                                        "success": bool(entry_lift.get("success")),
                                        "error": entry_lift.get("reason")
                                        or (entry_lift.get("retreat") or {}).get("error")
                                        or "",
                                        "escape_profile": entry_lift.get("escape_profile"),
                                        "event": entry_lift,
                                        "selected_recovery_goal": bridge_diag.get("selected_recovery_goal"),
                                        "selected_recovery_goal_reason": bridge_diag.get(
                                            "selected_recovery_goal_reason"
                                        ),
                                        "selected_recovery_goal_atoms": bridge_diag.get(
                                            "selected_recovery_goal_atoms"
                                        ),
                                        "selected_recovery_goal_surfaces": bridge_diag.get(
                                            "selected_recovery_goal_surfaces"
                                        ),
                                    }
                                )
                            events = (attempt.planner_backend.get("execution_trace") or {}).get("events") or []
                            rows = recovery_events_from_trace(events, query_idx=query_idx, skill_id=skill_id)
                            if rows:
                                for row in rows:
                                    writer.append_recovery(row)
                            else:
                                writer.append_recovery(
                                    recover_without_execution_event(
                                        attempt,
                                        query_idx=query_idx,
                                        skill_id=skill_id,
                                    )
                                )
                        if bool(getattr(result, "abort_episode", False)):
                            episode_abort = True
                            episode_abort_reason = str(
                                getattr(result, "abort_reason", "") or "recovery_abort_episode"
                            )
                            writer.append_recovery(
                                {
                                    "kind": "execution_bridge",
                                    "event": "recovery_abort_episode",
                                    "query_idx": query_idx,
                                    "skill_id": skill_id,
                                    "success": False,
                                    "error": episode_abort_reason,
                                }
                            )
                        done = _check_task_success(env, fallback_done=False)
                        action_plan.clear()
                        query_idx += 1
                        if episode_abort:
                            break
                        if done:
                            break
                        continue

                    action_plan.extend(action_chunk[: args.action_chunk])
                    query_idx += 1

                action = action_plan.popleft()
                obs, _, done, _ = env.step(action.tolist())
                done = _check_task_success(env, fallback_done=done)
                if done:
                    break

            video_path = ""
            if args.save_video and video_frames:
                import imageio.v2 as imageio

                video_path = str(writer.episode_dir / "video.mp4")
                imageio.mimsave(video_path, video_frames, fps=args.fps, macro_block_size=1)

            writer.write_episode_json(
                {
                    "task_id_1based": tid1,
                    "task_id": task_id,
                    "episode_idx": episode_idx,
                    "seed": episode_seed,
                    "base_seed": args.seed,
                    "episode_seed_start": args.episode_seed_start,
                    "init_state_idx": init_state_idx,
                    "task_description": str(engine_description),
                    "policy_prompt": str(task_description),
                    "source_suite": eval_task.source_suite,
                    "source_task_id_1based": eval_task.source_task_id_1based,
                    "generated_benchmark_dir": args.generated_benchmark_dir,
                    "generated_split": eval_task.generated_split,
                    "generated_task_id": eval_task.generated_task_id,
                    "generated_template": eval_task.generated_template,
                    "generated_manifest_row": eval_task.generated_metadata,
                    "success": bool(done),
                    "abort_episode": bool(episode_abort),
                    "abort_reason": episode_abort_reason,
                    "num_queries": query_idx,
                    "num_env_steps": last_t + 1 - args.num_steps_wait,
                    "recovery_calls": recovery_calls,
                    "skills_enabled": bool(args.enable_skills),
                    "skill_pack": skill_config_summary.get("skill_pack") or {},
                    "skill_index": str(skill_config.skill_index),
                    "capability_registry": str(skill_config.capability_registry or ""),
                    "capability_registry_summary": capability_registry_summary,
                    "force_recovery_query": args.force_recovery_query,
                    "diagnostic_signal_registry": str(skill_config.diagnostic_signal_registry or ""),
                    "diagnostic_signal_statuses": args.diagnostic_signal_statuses,
                    "predicate_registry": str(skill_config.predicate_registry or ""),
                    "predicate_adapter": str(skill_config.predicate_adapter or ""),
                    "video": video_path,
                    "query_trace": "query_trace.jsonl",
                    "recovery_trace": "recovery_trace.jsonl",
                    "frames": "frames",
                }
            )
            total_episodes += 1
            total_successes += int(bool(done))
            task_completed_episodes += 1
            task_successes += int(bool(done))
            logger.info("episode done success=%s recoveries=%d", done, recovery_calls)
            if should_early_stop_first_failures(
                completed_episodes=task_completed_episodes,
                successes=task_successes,
                first_n_failures=getattr(args, "early_stop_first_n_failures", 0),
            ):
                early_stop = {
                    "task_id_1based": tid1,
                    "source_task_id_1based": eval_task.source_task_id_1based,
                    "task_dir_name": eval_task.task_dir_name,
                    "task_description": str(engine_description),
                    "completed_episodes": task_completed_episodes,
                    "successes": task_successes,
                    "threshold": int(getattr(args, "early_stop_first_n_failures", 0) or 0),
                    "reason": (
                        f"first {task_completed_episodes} validation episodes all failed; "
                        "stopping early for Codex intervention"
                    ),
                }
                early_stops.append(early_stop)
                logger.warning("early stopping validation: %s", json.dumps(early_stop, ensure_ascii=False))
                break
        env.close()

    summary = {
        "episodes": total_episodes,
        "success": total_successes,
        "success_rate": total_successes / total_episodes if total_episodes else 0.0,
        "early_stops": early_stops,
        "params": {key: value for key, value in vars(args).items() if key != "pretrained_path"},
        "skill_config": skill_config_summary,
        "capability_registry_summary": capability_registry_summary,
        "pretrained_path": args.pretrained_path,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(json.dumps(summary, ensure_ascii=False, indent=2))
    if hasattr(policy, "close"):
        policy.close()


if __name__ == "__main__":
    main(parse_args())
