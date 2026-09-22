"""Single-DOF articulation model and checked path refinement (no GPU imports).

All transforms are frame-from-local matrices. Coordinates are metres/radians.
The frame is explicitly either ``world`` or ``robot_base``; the current observed
configuration is the reference, so MuJoCo's qpos0 need not be assumed to be zero.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

import numpy as np

from .mujoco_compat import model_names


class ArticulationError(ValueError):
    """An invalid model or infeasible articulation; never a successful fallback."""


def vector(value: Any, size: int) -> np.ndarray:
    out = np.asarray(value, dtype=float)
    if out.shape != (size,) or not np.isfinite(out).all():
        raise ArticulationError(f"expected finite vector of size {size}")
    return out


def transform(value: Any) -> np.ndarray:
    out = np.asarray(value, dtype=float)
    if out.shape != (4, 4) or not np.isfinite(out).all():
        raise ArticulationError("expected finite 4x4 transform")
    if not np.allclose(out[3], [0, 0, 0, 1], atol=1e-7):
        raise ArticulationError("invalid homogeneous transform")
    rot = out[:3, :3]
    if not np.allclose(rot.T @ rot, np.eye(3), atol=1e-5) or not np.isclose(np.linalg.det(rot), 1, atol=1e-5):
        raise ArticulationError("invalid rotation")
    return out


@dataclass
class ArticulatedPart:
    part_id: str
    joint_name: str
    joint_type: str
    body_name: str
    frame: str
    axis: list[float]
    anchor: list[float]
    reference_position: float
    joint_range: list[float]
    handle_reference: list[list[float]]
    open_range: list[float]
    closed_range: list[float]
    target_source: str
    handle_site: str
    moving_geom_ids: list[int]
    handle_geom_ids: list[int]
    grasps: list[list[list[float]]]
    handle_geom: str = ""

    def __post_init__(self) -> None:
        if not self.part_id or not self.joint_name or not self.body_name or not self.target_source:
            raise ArticulationError("invalid_articulation_binding: missing identity or target source")
        if bool(self.handle_site) == bool(self.handle_geom):
            raise ArticulationError("specify exactly one handle site or geometry frame")
        if self.joint_type not in {"slide", "hinge"} or self.frame not in {"world", "robot_base"}:
            raise ArticulationError("unsupported articulation type/frame")
        axis = vector(self.axis, 3)
        if not np.isclose(np.linalg.norm(axis), 1, atol=1e-5):
            raise ArticulationError("joint axis must be a unit vector")
        vector(self.anchor, 3)
        transform(self.handle_reference)
        limits = vector(self.joint_range, 2)
        if limits[0] >= limits[1] or not limits[0] <= self.reference_position <= limits[1]:
            raise ArticulationError("invalid joint range/reference")
        for interval in (self.open_range, self.closed_range):
            lo, hi = vector(interval, 2)
            if not limits[0] <= lo <= hi <= limits[1]:
                raise ArticulationError("target interval outside mechanical limits")
        if max(self.open_range[0], self.closed_range[0]) <= min(self.open_range[1], self.closed_range[1]):
            raise ArticulationError("open and closed intervals overlap")
        if not self.moving_geom_ids or not self.handle_geom_ids or not set(self.handle_geom_ids) <= set(self.moving_geom_ids):
            raise ArticulationError("invalid moving/handle geometry binding")
        if len(set(self.moving_geom_ids)) != len(self.moving_geom_ids):
            raise ArticulationError("duplicate moving geometry")
        if not self.grasps:
            raise ArticulationError("no_feasible_handle_grasp: no candidates configured")
        for grasp in self.grasps:
            transform(grasp)

    def to_dict(self) -> dict:
        return asdict(self)

    def target_range(self, goal: str) -> list[float]:
        if goal not in {"open", "closed"}:
            raise ArticulationError(f"unsupported articulation goal: {goal}")
        return self.open_range if goal == "open" else self.closed_range

    def mode(self, position: float) -> str:
        if not np.isfinite(position):
            raise ArticulationError("nonfinite articulation position")
        for goal in ("open", "closed"):
            lo, hi = self.target_range(goal)
            if lo <= position <= hi:
                return goal
        return "intermediate"

    def displacement(self, position: float) -> np.ndarray:
        if not np.isfinite(position) or not self.joint_range[0] <= position <= self.joint_range[1]:
            raise ArticulationError("articulation_joint_limit")
        delta = float(position - self.reference_position)
        axis, anchor = np.asarray(self.axis), np.asarray(self.anchor)
        out = np.eye(4)
        if self.joint_type == "slide":
            out[:3, 3] = axis * delta
        else:
            x, y, z = axis
            skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
            rotation = np.eye(3) + np.sin(delta) * skew + (1 - np.cos(delta)) * (skew @ skew)
            out[:3, :3] = rotation
            out[:3, 3] = anchor - rotation @ anchor
        return out

    def handle_pose(self, position: float) -> np.ndarray:
        return self.displacement(position) @ np.asarray(self.handle_reference)

    def in_frame(self, frame_from_current: Any, frame: str) -> ArticulatedPart:
        matrix = transform(frame_from_current)
        values = self.to_dict()
        values.update(
            frame=frame,
            axis=(matrix[:3, :3] @ self.axis).tolist(),
            anchor=(matrix[:3, :3] @ self.anchor + matrix[:3, 3]).tolist(),
            handle_reference=(matrix @ self.handle_reference).tolist(),
        )
        return ArticulatedPart(**values)


def pose_residual(actual: Any, desired: Any) -> tuple[float, float]:
    actual, desired = transform(actual), transform(desired)
    position = float(np.linalg.norm(actual[:3, 3] - desired[:3, 3]))
    rotation = actual[:3, :3].T @ desired[:3, :3]
    angle = float(np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1)))
    return position, angle


@dataclass(frozen=True)
class PathSettings:
    slide_step: float = 0.005
    hinge_step: float = 0.02
    joint_step: float = 0.04
    position_tolerance: float = 0.002
    rotation_tolerance: float = 0.02
    max_joint_jump: float = 0.25
    max_points: int = 4096

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if not np.isfinite(value) or value <= 0:
                raise ArticulationError(f"invalid path setting: {key}")


class ArticulationMotion(Protocol):
    """Backend must check self/world/part collision, including contact pairs.

    ``valid`` evaluates the scene at *position*, not its initial pose. Grasp
    transforms target the SAME end-effector link used by ``fk`` and ``ik``.
    """

    def set_position(self, position: float) -> None: ...
    def ik(self, pose: np.ndarray, seed: np.ndarray) -> np.ndarray | None: ...
    def fk(self, q: np.ndarray) -> np.ndarray: ...
    def valid(self, q: np.ndarray, position: float, contact: bool) -> bool: ...


def refine_articulation(
    part: ArticulatedPart, goal: str, grasp: Any, q_start: Any,
    motion: ArticulationMotion, settings: PathSettings | None = None,
) -> dict:
    """Refine a native operator and validate interpolated (q, s) samples.

    No collision callback means no solution. A set of successful independent
    IK calls is not a motion certificate; interpolated samples are checked too.
    """
    cfg = settings or PathSettings()
    grasp = transform(grasp)
    q_start = np.asarray(q_start, dtype=float)
    if q_start.ndim != 1 or not q_start.size or not np.isfinite(q_start).all():
        raise ArticulationError("invalid robot configuration")
    target = float(np.mean(part.target_range(goal)))
    step = cfg.slide_step if part.joint_type == "slide" else cfg.hinge_step
    count = max(2, int(np.ceil(abs(target - part.reference_position) / step)) + 1)
    if count > cfg.max_points:
        raise ArticulationError("articulation_path_budget")
    positions = np.linspace(part.reference_position, target, count)
    knots = [q_start]
    worst_position = worst_rotation = 0.0

    def check(q: np.ndarray, s: float) -> None:
        nonlocal worst_position, worst_rotation
        if q.shape != q_start.shape or not np.isfinite(q).all():
            raise ArticulationError("invalid IK output")
        error, angle = pose_residual(motion.fk(q), part.handle_pose(s) @ grasp)
        worst_position, worst_rotation = max(worst_position, error), max(worst_rotation, angle)
        if error > cfg.position_tolerance or angle > cfg.rotation_tolerance:
            raise ArticulationError("handle_pose_constraint_failed")
        if not motion.valid(q, float(s), True):
            raise ArticulationError("articulation_collision_or_joint_limit")

    check(q_start, float(positions[0]))
    for s in positions[1:]:
        motion.set_position(float(s))
        q = motion.ik(part.handle_pose(float(s)) @ grasp, knots[-1])
        if q is None:
            raise ArticulationError("articulation_ik_failed")
        q = np.asarray(q, dtype=float)
        if q.shape != q_start.shape or not np.isfinite(q).all():
            raise ArticulationError("invalid IK output")
        if np.max(np.abs(q - knots[-1])) > cfg.max_joint_jump:
            raise ArticulationError("articulation_ik_jump")
        knots.append(q)

    dense_q, dense_s = [q_start.tolist()], [float(positions[0])]
    for idx in range(1, len(knots)):
        # Check at least a midpoint even if the IK jump is small.
        n = max(2, int(np.ceil(np.max(np.abs(knots[idx] - knots[idx - 1])) / cfg.joint_step)))
        if len(dense_q) + n > cfg.max_points:
            raise ArticulationError("articulation_path_budget")
        for fraction in np.linspace(0, 1, n + 1)[1:]:
            q = knots[idx - 1] * (1 - fraction) + knots[idx] * fraction
            s = float(positions[idx - 1] * (1 - fraction) + positions[idx] * fraction)
            check(q, s)
            dense_q.append(q.tolist())
            dense_s.append(s)
    return {
        "positions": dense_q, "joint_positions": dense_s,
        "max_position_error": worst_position, "max_rotation_error": worst_rotation,
        "target_range": part.target_range(goal), "sampling": asdict(cfg),
    }


def read_articulation_structure(model: Any, data: Any) -> dict[str, dict]:
    """Read exact single-DOF non-robot joints, without guessing task bindings."""
    result = {}
    if model is None or data is None:
        return result
    names = model_names(model, "joint")
    geom_names = model_names(model, "geom")
    body_names = model_names(model, "body")
    site_names = model_names(model, "site")
    for jid, name in enumerate(names):
        if not name or str(name).startswith(("robot", "gripper")):
            continue
        kind = int(model.jnt_type[jid])
        if kind not in (2, 3):  # MuJoCo slide / hinge
            continue
        body = int(model.jnt_bodyid[jid])
        # Only a single independent DOF connected to a fixed ancestor chain.
        cursor, joint_count = body, 0
        while cursor:
            joint_count += int(model.body_jntnum[cursor])
            cursor = int(model.body_parentid[cursor])
        if joint_count != 1 or not bool(model.jnt_limited[jid]):
            continue
        descendants = {body}
        for bid in range(body + 1, int(model.nbody)):
            if int(model.body_parentid[bid]) in descendants and int(model.body_jntnum[bid]) == 0:
                descendants.add(bid)
        geometries = [i for i in range(int(model.ngeom)) if int(model.geom_bodyid[i]) in descendants
                      and (int(model.geom_contype[i]) or int(model.geom_conaffinity[i]))]
        sites = {}
        for sid, site_name in enumerate(site_names):
            if site_name and int(model.site_bodyid[sid]) in descendants:
                pose = np.eye(4)
                pose[:3, :3] = np.asarray(data.site_xmat[sid]).reshape(3, 3)
                pose[:3, 3] = data.site_xpos[sid]
                sites[str(site_name)] = pose.tolist()
        geom_poses = {}
        for gid in geometries:
            if geom_names[gid]:
                pose = np.eye(4)
                pose[:3, :3] = np.asarray(data.geom_xmat[gid]).reshape(3, 3)
                pose[:3, 3] = data.geom_xpos[gid]
                geom_poses[str(geom_names[gid])] = pose.tolist()
        result[str(name)] = {
            "joint_name": str(name), "joint_type": "slide" if kind == 2 else "hinge",
            "body_name": str(body_names[body]), "frame": "world",
            "axis": np.asarray(data.xaxis[jid], dtype=float).tolist(),
            "anchor": np.asarray(data.xanchor[jid], dtype=float).tolist(),
            "reference_position": float(data.qpos[int(model.jnt_qposadr[jid])]),
            "joint_range": np.asarray(model.jnt_range[jid], dtype=float).tolist(),
            "moving_geom_ids": geometries, "sites": sites,
            "geom_names": {str(geom_names[i]): i for i in geometries if geom_names[i]},
            "geom_poses": geom_poses,
        }
    return result


def bind_articulations(structure: dict, bindings: list[dict]) -> dict[str, ArticulatedPart]:
    result: dict[str, ArticulatedPart] = {}
    joints = set()
    for binding in bindings:
        try:
            raw = structure[binding["joint_name"]]
            values = {k: v for k, v in raw.items() if k not in {"sites", "geom_names", "geom_poses"}}
            site, geom = binding.get("handle_site", ""), binding.get("handle_geom", "")
            if bool(site) == bool(geom):
                raise ArticulationError("specify exactly one handle site or geometry frame")
            moving_geom_ids = list(raw["moving_geom_ids"])
            handle_geom_ids = [raw["geom_names"][name] for name in binding.get("handle_geoms", [])]
            # Some LIBERO assets expose a precise handle site but leave all
            # collision geoms unnamed.  The site is the authoritative grasp
            # reference in that case; retaining the moving collision set keeps
            # the dynamic obstacle model complete without guessing a name.
            if not handle_geom_ids and site:
                handle_geom_ids = list(moving_geom_ids)
            values.update(
                part_id=binding["part_id"],
                handle_reference=raw["sites"][site] if site else raw["geom_poses"][geom],
                moving_geom_ids=moving_geom_ids,
                handle_geom_ids=handle_geom_ids,
                open_range=binding["open_range"], closed_range=binding["closed_range"],
                target_source=binding["target_source"], grasps=binding["grasps"],
                handle_site=site, handle_geom=geom,
            )
            part = ArticulatedPart(**values)
        except (KeyError, TypeError) as exc:
            raise ArticulationError(f"invalid_articulation_binding: {exc}") from exc
        if part.part_id in result or part.joint_name in joints:
            raise ArticulationError("duplicate articulation part/joint binding")
        joints.add(part.joint_name)
        result[part.part_id] = part
    return result
