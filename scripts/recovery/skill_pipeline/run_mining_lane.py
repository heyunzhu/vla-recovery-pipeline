#!/usr/bin/env python3
"""Run one skill-mining task lane until it finishes or needs a Codex draft.

This is an orchestration helper only. It keeps Codex out of the online control
loop: the subprocess eval uses the normal skill-pipeline runner, then the
existing mining scorer decides whether the next step is pass/blocker/draft.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Run one mining lane.")
    parser.add_argument("--baseline_run_dir", required=True)
    parser.add_argument("--mine_dir", required=True)
    parser.add_argument(
        "--skill_pack",
        "--skill-pack",
        dest="skill_pack",
        default="",
        help="Optional isolated skill pack name/path. Use this instead of --skills_dir for pack-local mining.",
    )
    parser.add_argument("--skills_dir", default="")
    parser.add_argument(
        "--capability_registry",
        default="",
        help="Optional capability registry. If omitted, use capability_registry from --skills_dir/_index.yaml.",
    )
    parser.add_argument("--tasks", required=True, help="Task ids accepted by run_skill_mine.py, e.g. 11-20.")
    parser.add_argument("--repo_root", required=True)
    parser.add_argument("--python_bin", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--config_name", default="pi0_libero")
    parser.add_argument("--task_suite_name", default="libero_90")
    parser.add_argument("--generated_benchmark_dir", default="")
    parser.add_argument("--generated_split", default="smoke", choices=["smoke", "train", "validation", "all"])
    parser.add_argument("--gpu", required=True)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--num_trials", type=int, default=5)
    parser.add_argument(
        "--validation_early_stop_first_n_failures",
        type=int,
        default=5,
        help=(
            "During mining validation, stop a task after this many completed episodes "
            "if all have failed. Set <=0 to disable."
        ),
    )
    parser.add_argument("--seed", type=int, default=90)
    parser.add_argument(
        "--episode_seed_start",
        type=int,
        default=0,
        help="When >0, validation rollouts use and record consecutive seeds starting here.",
    )
    parser.add_argument("--action_chunk", type=int, default=5)
    parser.add_argument("--num_steps_wait", type=int, default=10)
    parser.add_argument("--max_recovery_calls", type=int, default=2)
    parser.add_argument("--max_recovery_steps", type=int, default=200)
    parser.add_argument("--max_replans", type=int, default=1)
    parser.add_argument(
        "--max_invalid_validation_retries",
        type=int,
        default=2,
        help="How many infrastructure-invalid validation runs to quarantine and rerun before failing the lane.",
    )
    parser.add_argument(
        "--archive_offline_scan_corpus",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Archive trace-only baseline/validation artifacts for future admission scans.",
    )
    parser.add_argument("--offline_scan_corpus_root", default="analysis_outputs/offline_trigger_corpus")
    return parser.parse_args()


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {message}", flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_json(cmd: list[str], *, env: dict[str, str], cwd: Path) -> dict[str, Any]:
    log("+ " + " ".join(cmd))
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(proc.stdout, end="", flush=True)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed with exit {proc.returncode}: {' '.join(cmd)}")
    text = proc.stdout.strip()
    if not text:
        raise RuntimeError("expected JSON output, got empty stdout")
    start = text.find("{")
    if start < 0:
        raise RuntimeError(f"expected JSON object in stdout: {text[:500]}")
    return json.loads(text[start:])


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def invalid_validation_quarantine_path(on_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = on_dir.with_name(f"{on_dir.name}_invalid_{stamp}")
    candidate = base
    idx = 1
    while candidate.exists():
        candidate = on_dir.with_name(f"{base.name}_{idx}")
        idx += 1
    return candidate


def quarantine_invalid_validation_dir(on_dir: str | Path, payload: dict[str, Any]) -> str:
    src = Path(on_dir)
    if not src.exists():
        return ""
    dest = invalid_validation_quarantine_path(src)
    shutil.move(str(src), str(dest))
    marker = dict(payload)
    marker["quarantined_at"] = now_iso()
    marker["original_on_dir"] = str(src)
    marker["quarantined_on_dir"] = str(dest)
    write_json(dest / "INVALID_VALIDATION.json", marker)
    return str(dest)


def lane_command_payload(
    args: argparse.Namespace,
    repo: Path,
    mine_dir: Path,
    *,
    argv: list[str] | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    command = list(argv or [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
    working_dir = Path(cwd or Path.cwd())
    return {
        "schema_version": 1,
        "kind": "skill_mining_lane_command",
        "created_at": now_iso(),
        "repo_root": str(repo),
        "mine_dir": str(mine_dir),
        "cwd": str(working_dir),
        "argv": command,
        "command_preview": shlex.join(command),
        "args": {key: value for key, value in sorted(vars(args).items())},
    }


def write_lane_command(
    args: argparse.Namespace,
    repo: Path,
    mine_dir: Path,
    *,
    argv: list[str] | None = None,
    cwd: Path | None = None,
) -> Path:
    path = mine_dir / "lane_command.json"
    write_json(path, lane_command_payload(args, repo, mine_dir, argv=argv, cwd=cwd))
    return path


def infer_actor_prompt(payload: dict[str, Any]) -> str:
    actor_prompt = str(payload.get("actor_prompt") or "").strip()
    if actor_prompt:
        return actor_prompt
    # Read legacy pack_json from archived WAIT_CODEX files, but new outputs are evidence_json-only.
    evidence_json = str(payload.get("evidence_json") or payload.get("pack_json") or "").strip()
    if not evidence_json:
        return ""
    return str(Path(evidence_json).parent / "actor_prompt.md")


def wait_codex_payload(mine_dir: Path, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["schema_version"] = 1
    enriched["event_type"] = "codex_intervention_required"
    enriched["source"] = source
    enriched["created_at"] = now_iso()
    enriched["mine_dir"] = str(mine_dir)
    enriched["wait_codex_json"] = str(mine_dir / "WAIT_CODEX.json")
    enriched["lane_command_json"] = str(mine_dir / "lane_command.json")
    actor_prompt = infer_actor_prompt(enriched)
    if actor_prompt:
        enriched["actor_prompt"] = actor_prompt
    evidence_json = str(enriched.get("evidence_json") or enriched.get("pack_json") or "").strip()
    if evidence_json:
        enriched["evidence_json"] = evidence_json
    enriched.pop("pack_json", None)
    return enriched


def write_wait_codex(mine_dir: Path, payload: dict[str, Any], *, source: str) -> Path:
    path = mine_dir / "WAIT_CODEX.json"
    write_json(path, wait_codex_payload(mine_dir, payload, source=source))
    return path


def build_child_env(args: argparse.Namespace, repo: Path, *, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    env["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
    env["OVERLAY_ROOT"] = str(repo)
    env["CUTAMP_RUNNER_PYTHON"] = str(repo / "scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh")
    env["PYTHONUNBUFFERED"] = "1"

    workspace = repo.parent.parent if repo.parent.name in {"code", "code_snapshots"} else repo.parent
    libero_pythonpath_root = env.get("LIBERO_PYTHONPATH_ROOT")
    libero_entry = str(Path(libero_pythonpath_root)) if libero_pythonpath_root else str(workspace / "LIBERO_src")
    pythonpath_entries = [
        str(repo),
        libero_entry,
        str(workspace / "openpi" / "src"),
    ]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    return env


# A cell's language-source protocol is chosen once at baseline time and inherited by every
# validation the lane runs, so w0 and the post-draft rounds cannot disagree with the baseline.
LANGUAGE_SOURCE_FLAGS = ("task_language_source", "engine_language_source")


def baseline_params(args: argparse.Namespace) -> dict[str, Any]:
    summary = Path(args.baseline_run_dir) / "summary.json"
    if not summary.exists():
        return {}
    try:
        return dict(json.loads(summary.read_text(encoding="utf-8")).get("params") or {})
    except (OSError, ValueError):
        return {}


def eval_command(args: argparse.Namespace, task_id: int, exp_name: str, log_dir: Path,
                 *, force_recovery_query: int = -1, episode_index_start: int = 0) -> list[str]:
    repo = Path(args.repo_root)
    out_dir = log_dir / exp_name
    cmd = [
        args.python_bin,
        str(repo / "scripts/recovery/skill_pipeline/run_skill_eval.py"),
        "--log_dir",
        str(log_dir),
        "--exp_name",
        exp_name,
        "--openvla_repo_root",
        str(repo),
        "--config_name",
        args.config_name,
        "--pretrained_path",
        args.model,
        "--task_suite_name",
        args.task_suite_name,
        "--task_ids",
        str(task_id),
        "--num_trials_per_task",
        str(args.num_trials),
        "--early_stop_first_n_failures",
        str(max(0, int(getattr(args, "validation_early_stop_first_n_failures", 5) or 0))),
        "--action_chunk",
        str(args.action_chunk),
        "--num_steps_wait",
        str(args.num_steps_wait),
        "--seed",
        str(args.seed),
        "--max_recovery_calls",
        str(args.max_recovery_calls),
        "--save_video",
        "--fps",
        str(args.fps),
        "--enable_mining_skills",
        *(
            [
                "--skill_pack",
                args.skill_pack,
            ]
            if args.skill_pack
            else []
        ),
        "--skill_index",
        str(Path(args.skills_dir) / "_index.yaml"),
        "--policy_in_process",
        "--force_recovery_query",
        str(force_recovery_query),
        "--max_recovery_steps",
        str(args.max_recovery_steps),
        "--max_replans",
        str(args.max_replans),
        "--num_particles",
        "128",
        "--particle_iters",
        "100",
        "--particle_lr",
        "0.045",
        "--min_success_fraction",
        "0.01",
        "--use_real_cutamp_backend",
        "--real_cutamp_require_feasible",
        "--real_cutamp_robot",
        "panda",
        "--real_cutamp_grasp_dof",
        "6",
        "--real_cutamp_num_particles",
        "64",
        "--real_cutamp_num_opt_steps",
        "40",
        "--real_cutamp_max_loop_dur",
        "20.0",
        "--real_cutamp_curobo_plan",
        "--real_cutamp_serialize_trajectories",
        "--prefer_real_cutamp_executable_plan",
        "--require_real_cutamp_executable_plan",
        "--real_cutamp_runner_python",
        str(repo / "scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh"),
        "--real_cutamp_runner_timeout_sec",
        "360.0",
        "--real_cutamp_debug_dir",
        str(out_dir / "cutamp_debug"),
        "--real_cutamp_table_proxy_profile",
        "thin_clipped_lowered",
        "--real_cutamp_static_context_collision_mode",
        "all",
    ]
    if int(args.episode_seed_start) > 0:
        cmd.extend(["--episode_seed_start", str(args.episode_seed_start)])
    if episode_index_start:
        cmd.extend(["--episode_index_start", str(episode_index_start)])
    if args.generated_benchmark_dir:
        cmd.extend(
            [
                "--generated_benchmark_dir",
                args.generated_benchmark_dir,
                "--generated_split",
                args.generated_split,
                "--generated_task_ids",
                str(task_id),
            ]
        )
    if args.capability_registry:
        cmd.extend(["--capability_registry", args.capability_registry])
    params = baseline_params(args)
    for key in LANGUAGE_SOURCE_FLAGS:
        if params.get(key):
            cmd.extend([f"--{key}", str(params[key])])
    return cmd


def export_command(args: argparse.Namespace, on_dir: Path) -> list[str]:
    repo = Path(args.repo_root)
    return [
        args.python_bin,
        str(repo / "scripts/recovery/skill_pipeline/export_annotated_skill_pipeline_videos.py"),
        "--run-dir",
        str(on_dir),
        "--out-dir",
        str(on_dir.parent / f"{on_dir.name}_annotated_recovery_marked"),
    ]


def _repo_relative_or_absolute(repo: Path, path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else repo / value


def archive_command(args: argparse.Namespace, run_dir: Path, name: str) -> list[str]:
    repo = Path(args.repo_root)
    return [
        args.python_bin,
        str(repo / "scripts/recovery/skill_pipeline/archive_offline_scan_corpus.py"),
        "--run-dir",
        str(run_dir),
        "--repo",
        str(repo),
        "--corpus-root",
        str(_repo_relative_or_absolute(repo, args.offline_scan_corpus_root)),
        "--name",
        name,
    ]


def archive_run(args: argparse.Namespace, run_dir: Path, name: str, *, env: dict[str, str], cwd: Path) -> None:
    if not bool(args.archive_offline_scan_corpus):
        return
    if not run_dir.exists():
        log(f"skip archive; run dir does not exist: {run_dir}")
        return
    subprocess.run(archive_command(args, run_dir, name), cwd=str(cwd), env=env, check=True)


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root)
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config

    if not args.skills_dir and not args.skill_pack:
        raise SystemExit("provide either --skills_dir or --skill_pack")
    skill_config = resolve_skill_config(
        skill_pack=args.skill_pack or None,
        skills_dir=args.skills_dir or None,
        capability_registry=args.capability_registry or None,
        repo=repo,
    )
    args.skills_dir = str(skill_config.skills_dir)
    if not args.capability_registry and skill_config.capability_registry:
        args.capability_registry = str(skill_config.capability_registry)

    mine_dir = Path(args.mine_dir)
    validation_dir = mine_dir / "validation"
    mine_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)
    write_lane_command(args, repo, mine_dir)

    env = build_child_env(args, repo)

    mine_cli = [
        args.python_bin,
        str(repo / "scripts/recovery/skill_pipeline/run_skill_mine.py"),
    ]
    common = [
        "--run_dir",
        args.baseline_run_dir,
        "--out_dir",
        str(mine_dir),
        *(
            [
                "--skill_pack",
                args.skill_pack,
            ]
            if args.skill_pack
            else []
        ),
        "--skills_dir",
        args.skills_dir,
        "--task_ids",
        args.tasks,
    ]
    if args.capability_registry:
        common.extend(["--capability_registry", args.capability_registry])
    if args.generated_benchmark_dir:
        common.extend(
            [
                "--generated_benchmark_dir",
                args.generated_benchmark_dir,
                "--generated_split",
                args.generated_split,
            ]
        )

    archive_run(
        args,
        Path(args.baseline_run_dir),
        f"mining_baseline_{Path(args.baseline_run_dir).name}",
        env=env,
        cwd=repo,
    )

    retry_path = mine_dir / "invalid_validation_retries.json"
    invalid_validation_retries: dict[str, int] = (
        json.loads(retry_path.read_text(encoding="utf-8")) if retry_path.exists() else {}
    )
    while True:
        step = run_json(mine_cli + ["step", *common], env=env, cwd=repo)
        status = str(step.get("status") or "")
        write_json(mine_dir / "last_step.json", step)
        if status == "done":
            log("lane done")
            return 0
        if status in {"need_draft", "awaiting_draft"}:
            log(f"lane waiting for Codex draft at task{int(step.get('awaiting_task') or 0):02d}")
            write_wait_codex(mine_dir, step, source="step")
            return 20
        if status not in {"need_validation", "awaiting_validation"}:
            raise RuntimeError(f"unexpected mining status: {status}")

        validation = dict(step.get("validation") or {})
        task_id = int(step.get("awaiting_task") or validation.get("task_id") or 0)
        if not task_id:
            raise RuntimeError(f"missing awaiting_task in step result: {step}")
        exp_name = str(validation.get("exp_name") or f"mine_val_task{task_id:02d}_w0")
        on_dir = validation_dir / exp_name
        summary_path = on_dir / "summary.json"

        if summary_path.exists():
            log(f"reuse existing validation summary: {summary_path}")
        else:
            process = subprocess.run(
                eval_command(args, task_id, exp_name, validation_dir),
                cwd=str(repo),
                env=env,
                check=False,
            )
            if process.returncode:
                failure = {"status": "invalid_validation", "task_id": task_id,
                           "on_dir": str(on_dir), "returncode": process.returncode,
                           "reason": "eval process failed before a valid completed run", "at": now_iso()}
                key = f"{task_id}:{exp_name}"
                invalid_validation_retries[key] = invalid_validation_retries.get(key, 0) + 1
                failure["quarantined_on_dir"] = quarantine_invalid_validation_dir(on_dir, failure)
                write_json(mine_dir / "last_invalid_validation.json", failure)
                write_json(retry_path, invalid_validation_retries)
                if invalid_validation_retries[key] > args.max_invalid_validation_retries:
                    raise RuntimeError(f"Invalid validation retry limit reached for {exp_name}; write not scored")
                continue

        subprocess.run(export_command(args, on_dir), cwd=str(repo), env=env, check=True)
        archive_run(args, on_dir, f"{mine_dir.name}_{on_dir.name}", env=env, cwd=repo)
        score = run_json(
            mine_cli
            + [
                "score",
                *common,
                "--task_id",
                str(task_id),
                "--on_dir",
                str(on_dir),
            ],
            env=env,
            cwd=repo,
        )
        write_json(mine_dir / "last_score.json", score)
        score_status = str(score.get("status") or "")
        if score_status == "invalid_validation":
            key = f"{task_id}:{exp_name}"
            invalid_validation_retries[key] = invalid_validation_retries.get(key, 0) + 1
            write_json(retry_path, invalid_validation_retries)
            quarantined = quarantine_invalid_validation_dir(on_dir, score)
            score["quarantined_on_dir"] = quarantined
            write_json(mine_dir / "last_score.json", score)
            write_json(mine_dir / "last_invalid_validation.json", score)
            if invalid_validation_retries[key] > int(args.max_invalid_validation_retries):
                raise RuntimeError(
                    f"validation {exp_name} stayed infrastructure-invalid after "
                    f"{invalid_validation_retries[key]} run(s): {score.get('reason') or score}"
                )
            log(
                f"validation {exp_name} invalid ({score.get('reason')}); "
                f"quarantined={quarantined or 'missing'}; rerunning same write"
            )
            continue
        if score_status in {"need_draft", "awaiting_draft"}:
            log(f"lane waiting for Codex draft at task{task_id:02d}")
            write_wait_codex(mine_dir, score, source="score")
            return 20


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"ERROR: {exc}")
        raise
