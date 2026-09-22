"""Experimental native cuTAMP domain extension for one articulated part.

Uses cuTAMP Fluent/TAMPOperator/Constraint and its task-plan search, not a
hand-written action sequence. Continuous refinement specializes the 1-DOF
manifold rather than sending new operators into pick/place-only RolloutFunction.
No global monkey-patching of the installed cuTAMP package is required.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import numpy as np

from .articulation import ArticulatedPart, ArticulationError, PathSettings, refine_articulation


def make_domain() -> SimpleNamespace:
    from cutamp.task_planning import Constraint, Fluent, Parameter, TAMPOperator

    # The deployed TiPToP cuTAMP fork interns GroundTAMPOperator instances in
    # a process-global cache keyed only by substitution names.  Our domain is
    # constructed per problem; without clearing that cache, a previous domain
    # can return an operator with the same q/grasp names but different fluents
    # and constraints.  Keep the workaround local to this extension instead of
    # changing process-wide environment state or monkey-patching cuTAMP.
    try:
        from cutamp.task_planning.tamp_structs import _GROUND_OP_CACHE
        _GROUND_OP_CACHE.clear()
    except (ImportError, AttributeError):
        pass

    part = Parameter("part", "articulated")
    grasp = Parameter("grasp", "grasp")
    qa, qb = Parameter("q_start", "conf"), Parameter("q_end", "conf")
    at = Fluent("At", [qa])
    empty = Fluent("HandEmpty")
    available = Fluent("CanGraspHandle", [part])
    candidate = Fluent("HandleCandidate", [part, grasp])
    held = Fluent("HandleGrasped", [part, grasp])
    release = Fluent("CanReleaseHandle", [part])
    opened, closed, middle = [Fluent(name, [part]) for name in ("Open", "Closed", "Intermediate")]
    need_open, need_close = [Fluent(name, [part]) for name in ("NeedsOpen", "NeedsClose")]

    constraints = {
        name: type(name, (Constraint,), {}) for name in (
            "HandlePoseConsistency", "ArticulationLimits", "ArticulationTarget",
            "ArticulatedCollisionFree", "ArticulatedMotion",
        )
    }
    operators = [TAMPOperator(
        "GraspHandle", [part, grasp, qa, qb],
        preconditions=[empty(), available(part), candidate(part, grasp), at(qa)],
        add_effects=[held(part, grasp), at(qb)],
        del_effects=[empty(), available(part), at(qa)],
        constraints=[constraints["HandlePoseConsistency"](part, grasp, qb),
                     constraints["ArticulatedCollisionFree"](part, qa, qb)],
    )]
    for goal, desired, needed, sources in (
        ("Open", opened, need_open, (closed, middle)),
        ("Close", closed, need_close, (opened, middle)),
    ):
        for source in sources:
            operators.append(TAMPOperator(
                f"{goal}ArticulatedFrom{source.name}", [part, grasp, qa, qb],
                preconditions=[held(part, grasp), source(part), needed(part), at(qa)],
                add_effects=[desired(part), release(part), at(qb)],
                del_effects=[source(part), needed(part), at(qa)],
                constraints=[cls(part, grasp, qa, qb) for cls in constraints.values()],
            ))
    operators.append(TAMPOperator(
        "ReleaseHandle", [part, grasp, qa],
        preconditions=[held(part, grasp), release(part), at(qa)],
        add_effects=[empty()], del_effects=[held(part, grasp), release(part)],
    ))
    return SimpleNamespace(
        operators=operators, constraints=constraints, at=at, empty=empty,
        available=available, candidate=candidate, opened=opened, closed=closed,
        middle=middle, need_open=need_open, need_close=need_close,
    )


def skeletons(part: ArticulatedPart, goal: str):
    from cutamp.task_planning import task_plan_generator

    domain = make_domain()
    mode = part.mode(part.reference_position)
    state_fluent = {"open": domain.opened, "closed": domain.closed, "intermediate": domain.middle}[mode]
    desired = domain.opened if goal == "open" else domain.closed
    needed = domain.need_open if goal == "open" else domain.need_close
    part.target_range(goal)  # Validate before calling the native planner.
    initial = {domain.at.ground("q0"), domain.empty.ground(), state_fluent.ground(part.part_id)}
    if mode != goal:
        initial.update({needed.ground(part.part_id), domain.available.ground(part.part_id)})
        initial.update(domain.candidate.ground(part.part_id, f"grasp{i}") for i in range(len(part.grasps)))
    target = frozenset({desired.ground(part.part_id), domain.empty.ground()})
    return task_plan_generator(frozenset(initial), target, domain.operators, max_plan_skeletons=len(part.grasps))


def solve(part: ArticulatedPart, goal: str, q_initial: Any, motion: Any,
          settings: PathSettings | None = None, max_seconds: float = 30.0) -> dict:
    """Sample native skeletons, refine their constraints, and return one plan.

    motion.approach and motion.retreat must return collision-checked joint paths
    in the part's frame. motion.valid also checks every final interpolated path.
    """
    if not np.isfinite(max_seconds) or max_seconds <= 0:
        raise ArticulationError("invalid planning budget")
    start, errors = time.monotonic(), []
    cfg = settings or PathSettings()
    for skeleton in skeletons(part, goal):
        if time.monotonic() - start > max_seconds:
            raise ArticulationError("articulation_planning_timeout")
        q = np.asarray(q_initial, dtype=float)
        if q.ndim != 1 or not q.size or not np.isfinite(q).all():
            raise ArticulationError("invalid q_initial")
        if not skeleton:
            return {"operators": [], "actions": [], "part": part.to_dict(), "goal": goal, "already_satisfied": True}
        actions, summary = [], []
        s, grasp = part.reference_position, None
        try:
            for op in skeleton:
                name = op.operator.name
                values = dict(zip([p.name for p in op.operator.parameters], op.values))
                summary.append({"name": name, "values": values, "constraints": [str(c) for c in op.constraints]})
                if name == "GraspHandle":
                    index = int(values["grasp"].removeprefix("grasp"))
                    grasp = np.asarray(part.grasps[index])
                    target = part.handle_pose(s) @ grasp
                    path = np.asarray(motion.approach(q, target, s), dtype=float)
                    _check_free_path(path, q, motion, s, True, cfg)
                    q = path[-1]
                    from .articulation import pose_residual
                    pe, re = pose_residual(motion.fk(q), target)
                    if pe > cfg.position_tolerance or re > cfg.rotation_tolerance:
                        raise ArticulationError("handle_approach_pose_failed")
                    actions.extend([
                        {"type": "trajectory", "phase": "approach", "positions": path.tolist(), "gripper": "open"},
                        {"type": "gripper", "phase": "grasp", "action": "close"},
                    ])
                elif name.startswith(("OpenArticulated", "CloseArticulated")):
                    refined = refine_articulation(part, goal, grasp, q, motion, cfg)
                    q = np.asarray(refined["positions"][-1])
                    s = refined["joint_positions"][-1]
                    actions.append({"type": "trajectory", "phase": "articulate", "gripper": "close", **refined})
                elif name == "ReleaseHandle":
                    actions.append({"type": "gripper", "phase": "release", "action": "open"})
                    path = np.asarray(motion.retreat(q, s), dtype=float)
                    _check_free_path(path, q, motion, s, True, cfg)
                    q = path[-1]
                    actions.append({"type": "trajectory", "phase": "retreat", "positions": path.tolist(), "gripper": "open"})
                else:
                    raise ArticulationError(f"unsupported_articulated_operator:{name}")
            return {"operators": summary, "actions": actions, "part": part.to_dict(), "goal": goal,
                    "sampling": vars(cfg), "failed_candidates": errors}
        except ArticulationError as exc:
            errors.append(str(exc))
    raise ArticulationError(f"no_feasible_articulated_plan:{errors}")


def _check_free_path(path, start, motion, s, contact, cfg):
    if path.ndim != 2 or path.shape[1:] != start.shape or len(path) < 2 or not np.isfinite(path).all():
        raise ArticulationError("invalid_free_motion_path")
    if len(path) > cfg.max_points or np.max(np.abs(path[0] - start)) > 1e-5:
        raise ArticulationError("free_motion_start_or_budget_mismatch")
    checked = 0
    for previous, current in zip(path[:-1], path[1:]):
        n = max(2, int(np.ceil(np.max(np.abs(current - previous)) / cfg.joint_step)))
        checked += n + 1
        if checked > cfg.max_points * 4:
            raise ArticulationError("free_motion_validation_budget")
        for f in np.linspace(0, 1, n + 1):
            if not motion.valid(previous * (1 - f) + current * f, s, contact):
                raise ArticulationError("free_motion_collision_or_joint_limit")


def solve_backend_problem(problem: Any, config: Any):
    from .real_cutamp_backend import RealCuTAMPBackendResult

    start = time.monotonic()
    diagnostics = {"backend": "cutamp_articulation", "experimental": True,
                   "continuous_solver": "single_dof_constrained_refinement"}
    try:
        if not problem.articulation_options.get("enabled", False):
            raise ArticulationError("articulation_extension_disabled")
        goals = [a for a in problem.goal_atoms if a.predicate.lower() in {"open", "closed"}]
        if len(goals) != 1 or any(a.predicate.lower() not in {"open", "closed", "handempty"} for a in problem.goal_atoms):
            raise ArticulationError("unsupported_mixed_articulation_goal")
        atom = goals[0]
        if len(atom.args) != 1 or atom.args[0] not in problem.articulations:
            raise ArticulationError("invalid_articulation_binding: unresolved goal part")
        if problem.current_grasp or any(str(a.get("predicate", "")).lower() in {"holding", "holdingwithgrasp"}
                                        for a in problem.init_atoms):
            raise ArticulationError("articulation_requires_handempty")
        if not any(str(a.get("predicate", "")).lower() == "handempty" for a in problem.init_atoms):
            raise ArticulationError("articulation_handempty_unconfirmed")
        part = ArticulatedPart(**problem.articulations[atom.args[0]])
        if part.frame != "robot_base":
            raise ArticulationError("articulation_requires_robot_base_frame")
        from .articulation_curobo import CuroboArticulationMotion
        motion = CuroboArticulationMotion(problem, part, config.robot)
        plan = solve(part, atom.predicate.lower(), problem.q_init, motion,
                     PathSettings(**problem.articulation_options.get("path_settings", {})), config.max_loop_dur)
        diagnostics.update({"operators": plan["operators"], "failed_candidates": plan.get("failed_candidates", [])})
        return RealCuTAMPBackendResult(
            available=True, feasible=True, num_satisfying=1, elapsed_sec=time.monotonic() - start,
            executable_plan=[{"type": "articulation", "label": f"{atom.predicate}({part.part_id})", "plan": plan}],
            diagnostics=diagnostics,
        )
    except (ImportError, ArticulationError, RuntimeError, ValueError, AttributeError, KeyError) as exc:
        return RealCuTAMPBackendResult(
            available=not isinstance(exc, ImportError), feasible=False,
            failure_reason=f"{type(exc).__name__}:{exc}", elapsed_sec=time.monotonic() - start, diagnostics=diagnostics,
        )
