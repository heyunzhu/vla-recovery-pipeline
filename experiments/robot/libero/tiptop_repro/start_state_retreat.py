"""Back the robot out of a configuration that is already in collision.

A recovery starts from wherever the policy left the arm. On LIBERO-Goal task04 the
policy has just pulled the top drawer open (progress 0.978) and the gripper is still
inside the drawer's front board: the attribution probe measures a 1.0 cm overlap with
``wooden_cabinet_1_cabinet_top``. cuTAMP then reports
``[Collision] robot_to_world <= 0.001 has 0/64 satisfying`` before it optimises
anything, because ``q_init`` is shared by all 64 particles, so no plan can start.

This module searches for a nearby collision-free configuration by numerically
minimising the deepest sphere/OBB overlap over the joints, using the same collision
world the solver uses. It is deliberately separate from the planner: backing out is a
motion problem, not a task problem, and it must happen *before* planning so the
planner sees a valid start state.

The search is a pure function of ``penetration_fn`` so it is unit tested without
cuRobo; see ``tests/test_start_state_retreat.py``. :class:`CollisionProbe` binds the
real world and robot.

It has to run in the py3.10 environment (cuTAMP/cuRobo). The CLI entry point is what
the py3.11 side calls over the same ``CUTAMP_RUNNER_PYTHON`` subprocess the backend
already uses:

    ROOT=<work> OVERLAY_ROOT=<repo> \\
      <repo>/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \\
      -m experiments.robot.libero.tiptop_repro.start_state_retreat \\
      --solve-json <problem.json> --out-json <retreat.json>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _clamp(q: np.ndarray, lower: Optional[np.ndarray], upper: Optional[np.ndarray]) -> np.ndarray:
    if lower is None or upper is None:
        return q
    return np.minimum(np.maximum(q, lower), upper)


def _numerical_gradient(
    penetration_fn: Callable[[Sequence[float]], float],
    q: np.ndarray,
    lower: Optional[np.ndarray],
    upper: Optional[np.ndarray],
    delta: float,
) -> np.ndarray:
    """Central-difference gradient of the penetration w.r.t. each joint."""
    gradient = np.zeros_like(q)
    for index in range(q.size):
        offset = np.zeros_like(q)
        offset[index] = delta
        plus = _clamp(q + offset, lower, upper)
        minus = _clamp(q - offset, lower, upper)
        span = float(np.linalg.norm(plus - minus))
        if span < 1e-9:
            continue
        gradient[index] = (penetration_fn(plus) - penetration_fn(minus)) / span
    return gradient


def retreat_configuration(
    penetration_fn: Callable[[Sequence[float]], float],
    q_init: Sequence[float],
    *,
    lower: Optional[Sequence[float]] = None,
    upper: Optional[Sequence[float]] = None,
    step_rad: float = 0.05,
    max_iters: int = 40,
    min_step_rad: float = 0.002,
    finite_diff_rad: float = 0.01,
    backtrack: int = 5,
) -> Dict[str, Any]:
    """Find a nearby configuration with non-positive penetration.

    Descends the numerically differentiated penetration, halving the step until it
    improves and growing it back when it does. When the gradient vanishes it tries
    single-joint moves instead, which handles a locally flat contact surface. Joint
    limits are respected, so the result is always a configuration the robot can hold.
    """
    lower_arr = None if lower is None else np.asarray(list(lower), dtype=float)
    upper_arr = None if upper is None else np.asarray(list(upper), dtype=float)
    q = _clamp(np.asarray(list(q_init), dtype=float), lower_arr, upper_arr)
    initial = float(penetration_fn(q))
    trace: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {
        "initial_penetration_m": initial,
        "needs_retreat": initial > 0.0,
        "free": initial <= 0.0,
        "q": [float(v) for v in q],
        "penetration_m": initial,
        "iterations": 0,
        "trace": trace,
    }
    if initial <= 0.0:
        return result

    best = initial
    step = float(step_rad)
    for iteration in range(1, int(max_iters) + 1):
        gradient = _numerical_gradient(penetration_fn, q, lower_arr, upper_arr, finite_diff_rad)
        norm = float(np.linalg.norm(gradient))
        if norm < 1e-9:
            # Flat contact: probe each joint in both directions and keep the best.
            candidates = []
            for index in range(q.size):
                for sign in (1.0, -1.0):
                    offset = np.zeros_like(q)
                    offset[index] = sign * step
                    candidates.append(_clamp(q + offset, lower_arr, upper_arr))
        else:
            direction = -gradient / norm
            candidates = [_clamp(q + step * direction, lower_arr, upper_arr)]

        improved = False
        for _ in range(max(1, int(backtrack))):
            scored = [(float(penetration_fn(candidate)), candidate) for candidate in candidates]
            value, candidate = min(scored, key=lambda item: item[0])
            if value < best - 1e-9:
                q, best, improved = candidate, value, True
                break
            step *= 0.5
            candidates = [_clamp(q + step * (candidate - q), lower_arr, upper_arr) for _, candidate in scored]
            if step < float(min_step_rad):
                break
        trace.append({"iteration": iteration, "penetration_m": best, "step_rad": step})
        if best <= 0.0 or not improved or step < float(min_step_rad):
            break
        step = min(step * 1.5, float(step_rad))

    result.update(
        {
            "free": best <= 0.0,
            "q": [float(v) for v in q],
            "penetration_m": best,
            "iterations": len(trace),
        }
    )
    return result


def joint_limits_of(robot_container: Any) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """``(lower, upper)`` joint limits of a cuTAMP robot container, or ``(None, None)``.

    cuTAMP keeps them as a CUDA tensor, so they have to come back to the host before
    numpy can look at them.
    """
    raw = getattr(robot_container, "joint_limits", None)
    if raw is None:
        return None, None
    if hasattr(raw, "detach"):
        raw = raw.detach().cpu().numpy()
    array = np.asarray(raw, dtype=float)
    if array.ndim != 2 or array.shape[0] != 2:
        return None, None
    return array[0].copy(), array[1].copy()


class CollisionProbe:
    """The solver's collision world plus the robot, as a penetration function."""

    def __init__(self, cfg: Any, problem: Any) -> None:
        from curobo.types.base import TensorDeviceType
        from cutamp.robots import load_robot_container
        from cutamp.utils.common import get_world_cfg

        from .collision_report import obb_boxes_from_world_config, robot_spheres_at, worst_obstacle
        from .real_cutamp_backend import RealCuTAMPBackend

        backend = RealCuTAMPBackend(cfg)
        env, name_map, goal_notes, geometry_debug = backend._build_env(problem)
        self.env = env
        self.name_map = name_map
        self.goal_notes = list(goal_notes or [])
        self.geometry_debug = geometry_debug
        self.world_cfg = get_world_cfg(env, include_movables=False)
        self.boxes = obb_boxes_from_world_config(self.world_cfg)
        self.tensor_args = TensorDeviceType()
        self.robot_container = load_robot_container(cfg.robot, self.tensor_args)
        self._spheres_at = robot_spheres_at
        self._worst = worst_obstacle
        self.lower, self.upper = joint_limits_of(self.robot_container)

    def describe(self, q: Sequence[float]) -> Tuple[float, str, int]:
        spheres = self._spheres_at(self.robot_container, self.tensor_args, q)
        return self._worst(spheres, self.boxes)

    def penetration(self, q: Sequence[float]) -> float:
        return float(self.describe(q)[0])

    def report(self, q: Sequence[float]) -> Dict[str, Any]:
        depth, name, sphere_index = self.describe(q)
        return {
            "collides": bool(depth > 0.0),
            "penetration_m": float(depth),
            "worst_obstacle": name,
            "sphere_index": int(sphere_index),
            "num_obstacles": len(self.boxes),
        }


def plan_retreat(probe: CollisionProbe, q_init: Sequence[float], **kwargs: Any) -> Dict[str, Any]:
    """Retreat search against the real world, with the obstacle named at the end."""
    before = probe.report(q_init)
    result = retreat_configuration(
        probe.penetration,
        q_init,
        lower=probe.lower,
        upper=probe.upper,
        **kwargs,
    )
    after = probe.report(result["q"])
    result["initial_report"] = before
    result["final_report"] = after
    result["needs_retreat"] = bool(before["collides"] and not np.allclose(
        np.asarray(result["q"], dtype=float), np.asarray(list(q_init), dtype=float), atol=1e-9
    ))
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solve-json", required=True, help="Serialized cuTAMP problem whose q_init to check.")
    parser.add_argument("--out-json", default="", help="Where to write the retreat result.")
    parser.add_argument("--max-iters", type=int, default=40)
    parser.add_argument("--step-rad", type=float, default=0.05)
    parser.add_argument("--min-step-rad", type=float, default=0.002)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    solve_json = pathlib.Path(args.solve_json).expanduser().resolve()
    payload = json.loads(solve_json.read_text(encoding="utf-8"))

    from .real_cutamp_backend import RealCuTAMPBackendConfig, _problem_from_dict

    cfg = RealCuTAMPBackendConfig(**payload.get("config", {}))
    problem = _problem_from_dict(payload["problem"])
    q_init = list(problem.q_init or [])
    if not q_init:
        print("no q_init in this problem")
        return 2

    probe = CollisionProbe(cfg, problem)
    result = plan_retreat(
        probe,
        q_init,
        max_iters=args.max_iters,
        step_rad=args.step_rad,
        min_step_rad=args.min_step_rad,
    )
    result["solve_json"] = str(solve_json)

    if not args.quiet:
        before, after = result["initial_report"], result["final_report"]
        print(f"problem        : {solve_json.name}")
        print(f"obstacles      : {before['num_obstacles']}")
        print(f"q_init         : {'IN COLLISION' if before['collides'] else 'collision-free'}"
              f"  ({before['penetration_m']:+.5f} m on {before['worst_obstacle'] or '<none>'})")
        if result["needs_retreat"]:
            print(f"retreat        : {'free' if result['free'] else 'STILL IN COLLISION'} "
                  f"after {result['iterations']} iters  ({after['penetration_m']:+.5f} m)")
            print(f"retreat q      : {[round(v, 4) for v in result['q']]}")
        else:
            print("retreat        : not needed")

    if args.out_json:
        out = pathlib.Path(args.out_json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"wrote {out}")
    return 0 if result["free"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
