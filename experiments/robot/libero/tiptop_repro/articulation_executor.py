"""Execute an already-refined native articulated plan through the LIBERO bridge."""
from __future__ import annotations

import numpy as np
from dataclasses import replace

from .articulation import ArticulatedPart, ArticulationError, pose_residual


def _articulation_goal_result(client, part, goal, require_done=False):
    """Accept the task predicate once the measured articulation is in its goal range."""
    if require_done and not client.done:
        return None
    check_success = getattr(getattr(client, "env", None), "check_success", None)
    joint = client.get_scene().joints.get(part.joint_name)
    lo, hi = part.target_range(goal)
    if not callable(check_success) or joint is None or not lo <= float(joint.qpos) <= hi:
        return None
    if not bool(check_success()):
        return None
    return {"success": True, "task_success": True, "joint_goal_satisfied": True,
            "cleanup_complete": False, "completion": "environment_task_success",
            "joint_position": float(joint.qpos), "target_range": [lo, hi]}


def _terminal_articulation_result(client, part, goal):
    """A benchmark may terminate on closure before release can be observed."""
    return _articulation_goal_result(client, part, goal, require_done=True)


def _spaced_progress_indices(values, step):
    """Select progress checkpoints without dropping the terminal target."""
    values = np.asarray(values, dtype=float).reshape(-1)
    if len(values) < 2:
        return []
    selected = []
    anchor = float(values[0])
    for index in range(1, len(values) - 1):
        if abs(float(values[index]) - anchor) >= float(step):
            selected.append(index)
            anchor = float(values[index])
    if not selected or selected[-1] != len(values) - 1:
        selected.append(len(values) - 1)
    return selected


def _contact_probe_prefix(values, indices, distance):
    """Number of Cartesian targets needed to test a short, real joint pull."""
    if not indices or float(distance) <= 0:
        return 0
    values = np.asarray(values, dtype=float).reshape(-1)
    start = float(values[0])
    for count, index in enumerate(indices, start=1):
        if abs(float(values[index]) - start) >= float(distance) - 1e-9:
            return count
    return len(indices)


def _directional_joint_progress(start, actual, expected):
    """Measured progress toward expected, positive in the commanded direction."""
    delta = float(expected) - float(start)
    if abs(delta) < 1e-12:
        return 0.0
    return (float(actual) - float(start)) * float(np.sign(delta))


def execute_articulated_plan(client, plan: dict, max_steps: int) -> dict:
    # Generic pick/place permits centimetre-scale near-goal handoff. A handle
    # grasp must actually arrive before closing; scope tighter tracking to this
    # action and restore the caller's configuration even on failure.
    original = getattr(client, "cfg", None)
    if original is None:
        return _execute_articulated_plan(client, plan, max_steps)
    profile = dict(plan.get("selected_grasp_profile") or {})
    if profile.get("precision_contact_tracking"):
        # This is the controller contract used by the validated lower-drawer closure.
        client.cfg = replace(
            original, trajectory_reached_threshold=0.003,
            trajectory_final_reached_threshold=0.0005,
            near_goal_position_m=0.0005, near_goal_orientation_rad=0.005,
            orientation_reached_threshold=0.03,
            orientation_final_reached_threshold=0.005,
            trajectory_waypoint_max_steps=90,
            trajectory_stall_window=30, trajectory_min_step_progress=0.000001,
        )
    else:
        client.cfg = replace(
            original, trajectory_final_reached_threshold=0.003,
            near_goal_position_m=0.003, near_goal_orientation_rad=0.05,
            orientation_final_reached_threshold=0.05,
            trajectory_stall_window=8, trajectory_min_step_progress=0.00005,
        )
    try:
        return _execute_articulated_plan(client, plan, max_steps)
    finally:
        client.cfg = original


def _execute_articulated_plan(client, plan: dict, max_steps: int) -> dict:
    from .libero_panda_frames import quat_wxyz_to_matrix, xyzw_to_wxyz

    start = client.num_env_steps
    part = ArticulatedPart(**plan["part"])
    lo, hi = part.target_range(plan["goal"])
    joint_tolerance = 0.015 if part.joint_type == "slide" else 0.07
    grip_reference = None

    def remaining():
        return max(0, int(max_steps) - (client.num_env_steps - start))

    def position():
        state = client.get_scene().joints.get(part.joint_name)
        if state is None or not np.isfinite(state.qpos):
            raise ArticulationError("articulation_joint_feedback_missing")
        return float(state.qpos)

    def grip_pose(require_contact=True):
        scene = client.get_scene()
        sides = set()
        for contact in scene.contacts:
            if any(contact.get(key) in part.handle_geom_ids for key in ("geom1_id", "geom2_id")):
                sides.add(contact.get("finger_side"))
        if require_contact and not {"left", "right"} <= sides:
            raise ArticulationError("handle_bilateral_contact_missing")
        raw = scene.articulation_structure.get(part.joint_name, {})
        key, name = ("sites", part.handle_site) if part.handle_site else ("geom_poses", part.handle_geom)
        if name not in raw.get(key, {}):
            raise ArticulationError("handle_pose_feedback_missing")
        handle = np.asarray(raw[key][name])  # actual world pose
        ee = np.eye(4)
        ee[:3, :3] = quat_wxyz_to_matrix(xyzw_to_wxyz(scene.ee_quat))
        ee[:3, 3] = scene.ee_pos
        return np.linalg.inv(handle) @ ee

    def command_profile_width(profile, key, steps, label, hold_pose):
        method = getattr(client, "command_gripper_half_width", None)
        if not callable(method):
            raise ArticulationError("gripper_half_width_control_unavailable")
        if remaining() < int(steps):
            raise ArticulationError("articulation_execution_budget")
        result = method(float(profile[key]), int(steps), label, hold_pose=hold_pose)
        if not result.get("success"):
            raise ArticulationError(result.get("error") or "articulation_gripper_failed")
        return result

    try:
        if abs(position() - part.reference_position) > joint_tolerance:
            raise ArticulationError("stale_articulation_plan")
        actions = plan.get("actions", [])
        if not actions and not plan.get("already_satisfied"):
            raise ArticulationError("empty_articulation_plan")
        for action in actions:
            if remaining() <= 0:
                raise ArticulationError("articulation_execution_budget")
            if client.done:
                terminal = _terminal_articulation_result(client, part, plan["goal"])
                if terminal is not None:
                    return terminal
                # Cannot verify a release/retreat after the environment ends.
                raise ArticulationError("environment_terminated_before_articulation_cleanup")
            phase = action["phase"]
            if action["type"] == "gripper":
                profile = dict(action.get("grasp_profile") or {})
                if action["action"] == "progressive_contact_close":
                    close_steps = min(
                        remaining(), int(profile.get("nominal_contact_steps", client.cfg.grasp_close_steps))
                    )
                    command_profile_width(
                        profile, "nominal_contact_half_width_m", close_steps,
                        "grasp_handle:nominal_contact", True,
                    )
                    squeeze_steps = int(profile["squeeze_steps"])
                    if remaining() < squeeze_steps:
                        raise ArticulationError("articulation_execution_budget")
                    for index, width in enumerate(np.linspace(
                        float(profile["nominal_contact_half_width_m"]),
                        float(profile["squeeze_command_half_width_m"]), squeeze_steps,
                    )):
                        method = getattr(client, "command_gripper_half_width", None)
                        result = method(float(width), 1, f"grasp_handle:squeeze:{index}", hold_pose=True)
                        if not result.get("success"):
                            raise ArticulationError(result.get("error") or "articulation_gripper_failed")
                    grip_reference = grip_pose(bool(profile.get("require_bilateral_distal_contact", True)))
                    result = {"success": True}
                elif action["action"] == "close":
                    result = client.close_gripper(steps=min(remaining(), int(client.cfg.grasp_close_steps)), label="grasp_handle")
                    if result.get("success"):
                        grip_reference = grip_pose()
                elif action["action"] == "open":
                    if remaining() < 2:
                        raise ArticulationError("articulation_execution_budget")
                    clear_width = getattr(client, "set_gripper_half_width_target", None)
                    if callable(clear_width):
                        clear_width(None)
                    result = client.open_gripper(steps=min(remaining() // 2, 10), label="release_handle")
                    grip_reference = None
                else:
                    raise ArticulationError("unknown_articulation_gripper_action")
                if not result.get("success"):
                    raise ArticulationError(result.get("error") or "articulation_gripper_failed")
                continue
            if action["type"] != "trajectory":
                raise ArticulationError("unknown_articulation_action")
            path = np.asarray(action["positions"], dtype=float)
            expected = action.get("joint_positions")
            if path.ndim != 2 or not len(path) or not np.isfinite(path).all():
                raise ArticulationError("invalid_articulation_trajectory")
            if phase == "articulate" and (grip_reference is None or expected is None or len(expected) != len(path)):
                raise ArticulationError("invalid_articulation_contact_phase")
            profile = dict(action.get("grasp_profile") or {})
            if phase == "approach" and "opening_half_width_m" in profile:
                command_profile_width(profile, "opening_half_width_m", min(30, remaining()),
                                      "grasp_handle:prepare_opening", False)
            hold = client.cfg.gripper_close_value if action["gripper"] == "close" else client.cfg.gripper_open_value
            if phase == "articulate" and profile.get("execution_mode") == "cartesian_handle_follow":
                if part.joint_type != "slide":
                    raise ArticulationError("cartesian_handle_follow_requires_slide_joint")
                raw = client.get_scene().articulation_structure.get(part.joint_name, {})
                axis = np.asarray(raw.get("axis", []), dtype=float)
                if axis.shape != (3,) or not np.isfinite(axis).all() or not np.isclose(np.linalg.norm(axis), 1, atol=1e-5):
                    raise ArticulationError("articulation_world_axis_feedback_missing")
                start_scene = client.get_scene()
                start_ee = np.asarray(start_scene.ee_pos[:3], dtype=float)
                start_quat = np.asarray(start_scene.ee_quat, dtype=float)
                start_joint = float(expected[0])
                step = float(profile.get("cartesian_waypoint_step_m", 0.005))
                indices = _spaced_progress_indices(expected, step)
                targets = [
                    {
                        "position": (start_ee + axis * (float(expected[idx]) - start_joint)).tolist(),
                        "quat_xyzw": start_quat.tolist(),
                    }
                    for idx in indices
                ]
                probe_distance = float(profile.get("contact_probe_distance_m", 0.0))
                probe_count = _contact_probe_prefix(expected, indices, probe_distance)
                batches = [targets]
                if 0 < probe_count < len(targets):
                    batches = [targets[:probe_count], targets[probe_count:]]
                result = {"success": True}
                for batch_index, batch in enumerate(batches):
                    result = client.execute_cartesian_pose_waypoints(
                        batch, gripper=0.0, max_steps=remaining(), label=f"articulation:{phase}",
                    )
                    satisfied = _articulation_goal_result(client, part, plan["goal"])
                    if satisfied is not None:
                        satisfied.update({"selected_grasp_profile": profile.get("id"),
                                          "execution_mode": "cartesian_handle_follow"})
                        return satisfied
                    if not result.get("success"):
                        raise ArticulationError(result.get("error") or "articulation_tracking_failed")
                    if probe_count and batch_index == 0:
                        expected_probe = float(expected[indices[probe_count - 1]])
                        actual_probe = position()
                        measured = _directional_joint_progress(start_joint, actual_probe, expected_probe)
                        minimum = float(profile.get("contact_probe_min_progress_m", 0.0))
                        print(
                            "[contact-probe] "
                            f"joint_start={start_joint:.6f} joint_actual={actual_probe:.6f} "
                            f"joint_expected={expected_probe:.6f} measured={measured:.6f} "
                            f"minimum={minimum:.6f}",
                            flush=True,
                        )
                        if measured < minimum:
                            raise ArticulationError(
                                "handle_contact_probe_no_progress: "
                                f"measured={measured:.6f}, minimum={minimum:.6f}, "
                                f"joint={actual_probe:.6f}, expected={expected_probe:.6f}"
                            )
                        pe, re = pose_residual(grip_pose(), grip_reference)
                        if pe > 0.01 or re > 0.1:
                            raise ArticulationError("handle_relative_pose_drift_during_contact_probe")
                satisfied = _articulation_goal_result(client, part, plan["goal"])
                if satisfied is not None:
                    satisfied.update({"selected_grasp_profile": profile.get("id"),
                                      "execution_mode": "cartesian_handle_follow"})
                    return satisfied
                actual_final = position()
                if abs(actual_final - float(expected[-1])) > joint_tolerance:
                    raise ArticulationError(
                        "handle_slip_or_no_progress: "
                        f"joint={actual_final:.6f}, expected={float(expected[-1]):.6f}, "
                        f"error={abs(actual_final - float(expected[-1])):.6f}"
                    )
                pe, re = pose_residual(grip_pose(), grip_reference)
                if pe > 0.01 or re > 0.1:
                    raise ArticulationError("handle_relative_pose_drift")
                continue
            if phase != "articulate":
                result = client.execute_joint_impedance_path(
                    path, max_steps=remaining(), gripper=float(hold),
                    label=f"articulation:{phase}", track_full_pose=True,
                    preserve_absolute_orientation=True,
                )
                satisfied = _articulation_goal_result(client, part, plan["goal"])
                if satisfied is not None:
                    return satisfied
                if not result.get("success"):
                    raise ArticulationError(result.get("error") or "articulation_tracking_failed")
                continue
            # Execute short segments: do not compress away the constrained path
            # or run it to completion before checking slip/joint progress.
            for idx in range(1, len(path)):
                if remaining() <= 0:
                    raise ArticulationError("articulation_execution_budget")
                result = client.execute_joint_impedance_path(
                    path[idx:idx + 1], max_steps=min(remaining(), client.cfg.trajectory_waypoint_max_steps),
                    gripper=float(hold), label=f"articulation:{phase}:{idx}", track_full_pose=True,
                    preserve_absolute_orientation=True,
                )
                satisfied = _articulation_goal_result(client, part, plan["goal"])
                if satisfied is not None:
                    return satisfied
                if not result.get("success"):
                    raise ArticulationError(result.get("error") or "articulation_tracking_failed")
                if phase == "articulate":
                    if abs(position() - float(expected[idx])) > joint_tolerance:
                        raise ArticulationError("handle_slip_or_no_progress")
                    pe, re = pose_residual(grip_pose(), grip_reference)
                    if pe > 0.01 or re > 0.1:
                        raise ArticulationError("handle_relative_pose_drift")
        # Retreat provides post-release observations without teleporting a joint.
        actual = position()
        if not lo <= actual <= hi:
            raise ArticulationError("articulation_target_not_reached")
        if not client.get_scene().gripper_open:
            raise ArticulationError("articulation_handempty_not_confirmed")
        return {"success": True, "joint_position": actual, "target_range": [lo, hi], "cleanup_complete": True}
    except (ArticulationError, KeyError, ValueError) as exc:
        return {"success": False, "error": str(exc)}
