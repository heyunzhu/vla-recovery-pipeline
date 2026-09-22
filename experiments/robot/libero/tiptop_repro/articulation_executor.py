"""Execute an already-refined native articulated plan through the LIBERO bridge."""
from __future__ import annotations

import numpy as np

from .articulation import ArticulatedPart, ArticulationError, pose_residual


def execute_articulated_plan(client, plan: dict, max_steps: int) -> dict:
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
                # Cannot verify a release/retreat after the environment ends.
                raise ArticulationError("environment_terminated_before_articulation_cleanup")
            phase = action["phase"]
            if action["type"] == "gripper":
                if action["action"] == "close":
                    result = client.close_gripper(steps=min(remaining(), int(client.cfg.grasp_close_steps)), label="grasp_handle")
                    if result.get("success"):
                        grip_reference = grip_pose()
                elif action["action"] == "open":
                    if remaining() < 2:
                        raise ArticulationError("articulation_execution_budget")
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
            hold = client.cfg.gripper_close_value if action["gripper"] == "close" else client.cfg.gripper_open_value
            # Execute short segments: do not compress away the constrained path
            # or run it to completion before checking slip/joint progress.
            for idx in range(1, len(path)):
                if remaining() <= 0:
                    raise ArticulationError("articulation_execution_budget")
                result = client.execute_joint_impedance_path(
                    path[idx:idx + 1], max_steps=min(remaining(), client.cfg.trajectory_waypoint_max_steps),
                    gripper=float(hold), label=f"articulation:{phase}:{idx}", track_full_pose=True,
                )
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
        return {"success": True, "joint_position": actual, "target_range": [lo, hi]}
    except (ArticulationError, KeyError, ValueError) as exc:
        return {"success": False, "error": str(exc)}
