"""Attribute an articulation grasp IK failure to reachability or collision geometry.

The tool evaluates the same end-effector target with complementary solver settings:

* multi-seed IK without an environment world (kinematic/self-collision check);
* the articulation runtime IK with its normal collision world;
* the articulation runtime IK after replacing that world with an empty one; and
* multi-seed IK with the normal runtime world.

The target can come from the first grasp in a recorded problem's articulation
binding, or from a row in a contact-IK candidate JSON file.  This makes the
diagnostic useful both for capability admission and for new-grasp discovery.

Run this inside the cuTAMP Python 3.10 overlay, for example::

    scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \
      scripts/recovery/skill_pipeline/inspect_articulation_ik.py \
      --solve-json /path/to/problem.json --source binding --out-json result.json

    scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \
      scripts/recovery/skill_pipeline/inspect_articulation_ik.py \
      --solve-json /path/to/problem.json --source contact \
      --contact-ik /path/to/contact_ik.json --candidate 8
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from typing import Any

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.tiptop_repro.articulation import ArticulatedPart  # noqa: E402
from experiments.robot.libero.tiptop_repro.collision_report import _load_problem  # noqa: E402


def _bool_count(result: Any) -> tuple[bool, int]:
    success = result.success.reshape(-1)
    return bool(success.any().item()), int(success.sum().item())


def _solve_multi_seed(solver: Any, pose: Any) -> tuple[bool, int, str]:
    """Use the first pose-solving API exposed by the installed cuRobo build."""
    errors: list[str] = []
    for name in ("solve_batch", "solve_pose", "solve_any"):
        method = getattr(solver, name, None)
        if method is None:
            continue
        try:
            ok, count = _bool_count(method(pose))
            return ok, count, name
        except Exception as exc:  # noqa: BLE001 - this is a diagnostic boundary
            errors.append(f"{name}:{type(exc).__name__}:{exc}")
    raise RuntimeError("no compatible cuRobo IK call succeeded: " + "; ".join(errors))


def _target_from_args(problem: Any, part: ArticulatedPart, args: argparse.Namespace) -> tuple[np.ndarray, float, dict[str, Any]]:
    binding = problem.articulation_options["bindings"][0]
    if args.source == "binding":
        handle_pose = part.handle_pose(part.reference_position)
        grasp = np.asarray(binding["grasps"][args.grasp_index], dtype=float)
        target = handle_pose @ grasp
        return target, float(args.opening), {
            "source": "binding",
            "grasp_index": args.grasp_index,
            "handle_xyz": handle_pose[:3, 3].tolist(),
        }

    if args.contact_ik is None:
        raise ValueError("--contact-ik is required when --source=contact")
    payload = json.loads(args.contact_ik.read_text(encoding="utf-8"))
    try:
        row = next(row for row in payload["rows"] if int(row["candidate_id"]) == args.candidate)
    except StopIteration as exc:
        raise ValueError(f"candidate {args.candidate} is absent from {args.contact_ik}") from exc
    target = np.asarray(row["target_curobo"], dtype=float)
    opening = float(row.get("opening") or args.opening)
    return target, opening, {"source": "contact", "candidate": args.candidate}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solve-json", required=True, type=pathlib.Path)
    parser.add_argument("--source", choices=("binding", "contact"), default="binding")
    parser.add_argument("--contact-ik", type=pathlib.Path)
    parser.add_argument("--candidate", type=int, default=8)
    parser.add_argument("--grasp-index", type=int, default=0)
    parser.add_argument("--opening", type=float, default=0.03)
    parser.add_argument("--out-json", type=pathlib.Path)
    args = parser.parse_args()

    import curobo
    import torch
    from curobo.geom.types import WorldConfig
    from curobo.types.math import Pose
    from curobo.wrap.reacher.ik_solver import IKSolver, IKSolverConfig
    from curobo.wrap.reacher.motion_gen import MotionGen, MotionGenConfig
    from cutamp.robots.franka import franka_curobo_cfg
    from experiments.robot.libero.tiptop_repro.articulation_curobo import CuroboArticulationMotion

    cfg, problem = _load_problem(args.solve_json)
    binding = problem.articulation_options["bindings"][0]
    part = ArticulatedPart(**problem.articulations[binding["part_id"]])
    q_init = np.asarray(problem.q_init, dtype=float)
    target, opening, target_meta = _target_from_args(problem, part, args)
    pose = Pose.from_matrix(torch.tensor([target], device="cuda", dtype=torch.float32))

    locked_cfg = copy.deepcopy(franka_curobo_cfg())
    locked_cfg["robot_cfg"]["kinematics"]["lock_joints"] = {
        "panda_finger_joint1": opening,
        "panda_finger_joint2": opening,
    }
    report: dict[str, Any] = {
        "solve_json": str(args.solve_json),
        "curobo_version": getattr(curobo, "__version__", "unknown"),
        "target": target.tolist(),
        "target_xyz": target[:3, 3].tolist(),
        "opening": opening,
        **target_meta,
        "checks": {},
    }

    def record(name: str, fn: Any) -> None:
        try:
            value = fn()
            report["checks"][name] = value
        except Exception as exc:  # noqa: BLE001 - preserve all four diagnostic results
            report["checks"][name] = {
                "success": False,
                "error": f"{type(exc).__name__}:{exc}",
            }

    def no_world_multi_seed() -> dict[str, Any]:
        solver = IKSolver(IKSolverConfig.load_from_robot_config(
            locked_cfg,
            world_model=None,
            num_seeds=64,
            use_cuda_graph=False,
            self_collision_check=True,
            self_collision_opt=True,
            position_threshold=0.001,
            rotation_threshold=0.01,
            seed=90,
        ))
        ok, count, api = _solve_multi_seed(solver, pose)
        return {"success": ok, "solutions": count, "api": api}

    motion = CuroboArticulationMotion(problem, part, cfg.robot)

    def runtime_world_single_seed() -> dict[str, Any]:
        solution = motion.ik(target, q_init)
        return {"success": solution is not None}

    def empty_world_single_seed() -> dict[str, Any]:
        empty_motion = CuroboArticulationMotion(problem, part, cfg.robot)
        empty_motion.motion.update_world(WorldConfig(cuboid=[]))
        solution = empty_motion.ik(target, q_init)
        result: dict[str, Any] = {"success": solution is not None}
        if solution is not None:
            result["fk_xyz"] = empty_motion.fk(solution)[:3, 3].tolist()
        return result

    def runtime_world_multi_seed() -> dict[str, Any]:
        solver = MotionGen(MotionGenConfig.load_from_robot_config(
            robot_cfg=locked_cfg,
            world_model=motion._world(),
            use_cuda_graph=False,
            collision_activation_distance=0.0,
        )).ik_solver
        ok, count, api = _solve_multi_seed(solver, pose)
        return {"success": ok, "solutions": count, "api": api}

    record("no_world_multi_seed", no_world_multi_seed)
    record("runtime_world_single_seed", runtime_world_single_seed)
    record("empty_world_single_seed", empty_world_single_seed)
    record("runtime_world_multi_seed", runtime_world_multi_seed)

    no_world_ok = report["checks"]["no_world_multi_seed"].get("success", False)
    normal_ok = report["checks"]["runtime_world_multi_seed"].get("success", False)
    if not no_world_ok:
        report["diagnosis"] = "target_unreachable_or_self_collision"
    elif not normal_ok:
        report["diagnosis"] = "environment_collision_world_rejects_target"
    else:
        report["diagnosis"] = "target_reachable_with_runtime_world"

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered, flush=True)
    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
