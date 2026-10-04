"""Temporal visual evidence; visible motion/proximity never proves contact."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json

import numpy as np

from .perception_artifact import rgb_sha256
from .rgbd_scene_provider import _frame_digest


class VisualTemporalDiagnostics:
    def __init__(self):
        self.reset()

    def reset(self):
        self._context = self._key = self._digest = self._result = None
        self._previous = None
        self._following_intervals = self._stable_goal_intervals = 0

    def observe(self, frame, handoff):
        snapshot = f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}"
        if (handoff.snapshot_id != snapshot or handoff.source != "rgbd"
                or handoff.episode_id != frame.episode_id or handoff.env_step != frame.env_step
                or handoff.camera_id != frame.camera_id or handoff.timestamp_s != frame.timestamp_s
                or handoff.calibration_version != frame.calibration_version
                or handoff.frame_rgb_sha256 != rgb_sha256(frame)
                or handoff.robot_state != dict(frame.robot_state)):
            raise ValueError("temporal handoff does not match RGB-D frame")
        context = (frame.episode_id, frame.camera_id, handoff.task_language,
                   handoff.perception_backend_id)
        # Scene refusal can omit backend identity. It still invalidates continuity.
        if self._context is not None and context[:3] != self._context[:3]:
            raise ValueError("reset temporal diagnostics before changing episode/camera/language")
        digest = (_frame_digest(frame), hashlib.sha256(json.dumps(
            dataclasses.asdict(handoff), sort_keys=True, allow_nan=False).encode()).digest())
        key = (frame.episode_id, frame.env_step, frame.camera_id)
        if key == self._key:
            if digest != self._digest:
                raise ValueError("temporal evidence changed for cached frame")
            return copy.deepcopy(self._result)
        if self._key is not None and frame.env_step <= self._key[1]:
            raise ValueError("temporal diagnostics require increasing environment steps")
        result = dict(snapshot_id=snapshot, evidence_kind="visible_motion_and_proximity",
                      holding_verified=False, goal_verified=False, planning_allowed=False,
                      holding=dict(status="insufficient_evidence", reason="first_observation"),
                      goal=dict(status="insufficient_evidence", reason="first_observation"),
                      unresolved_checks=["contact_or_attachment", "external_bottom_geometry",
                                         "support_contact_and_footprint", "task_attributes"])
        objects = {o.id: o for o in handoff.visible_objects}
        binding = handoff.binding
        target = objects.get(binding.target_id) if binding else None
        goal = objects.get(binding.goal_id) if binding else None
        eligible = lambda o: (o is not None and o.validity == "observed"
                             and o.last_seen_step == frame.env_step
                             and o.identity_status in {"new", "tracked"}
                             and o.visible_centroid_world_m is not None
                             and o.visible_bounds_world_m is not None
                             and np.isfinite(o.visible_centroid_world_m).all()
                             and np.isfinite(o.visible_bounds_world_m).all()
                             and np.all(np.asarray(o.visible_bounds_world_m)[0] <= np.asarray(o.visible_bounds_world_m)[1])
                             and o.depth_valid_fraction is not None and 0.8 <= o.depth_valid_fraction <= 1)
        if handoff.status != "visual_id_candidate" or not eligible(target) or not eligible(goal):
            for name in ("holding", "goal"):
                result[name]["reason"] = "current_binding_or_depth_unavailable"
            self._previous = None
            self._following_intervals = self._stable_goal_intervals = 0
        else:
            for name, shape in (("robot0_eef_pos", (3,)), ("robot0_eef_quat", (4,)),
                                ("robot0_gripper_qpos", (2,))):
                value = np.asarray(frame.robot_state[name])
                if value.shape != shape or not np.isfinite(value).all():
                    raise ValueError("invalid temporal robot proprioception")
            current = dict(context=context, timestamp=frame.timestamp_s,
                calibration=frame.calibration_version, K=frame.K.copy(), T=frame.T_world_camera.copy(),
                target_id=target.id, goal_id=goal.id,
                target=np.array(target.visible_centroid_world_m), goal=np.array(goal.visible_centroid_world_m),
                target_bounds=np.array(target.visible_bounds_world_m), goal_bounds=np.array(goal.visible_bounds_world_m),
                ee=np.array(frame.robot_state["robot0_eef_pos"]),
                quat=np.array(frame.robot_state["robot0_eef_quat"]),
                aperture=float(np.sum(frame.robot_state["robot0_gripper_qpos"])))
            previous = self._previous
            if previous is not None:
                dt = current["timestamp"] - previous["timestamp"]
                continuous = (0.05 <= dt <= 0.5 and current["context"] == previous["context"]
                    and current["target_id"] == previous["target_id"] and current["goal_id"] == previous["goal_id"]
                    and target.identity_status == "tracked" and goal.identity_status == "tracked"
                    and current["calibration"] == previous["calibration"]
                    and np.array_equal(current["K"], previous["K"])
                    and np.array_equal(current["T"], previous["T"]))
                if not continuous:
                    for name in ("holding", "goal"):
                        result[name]["reason"] = "identity_camera_calibration_or_time_discontinuity"
                    self._following_intervals = self._stable_goal_intervals = 0
                else:
                    self._measure(previous, current, binding, result)
            self._previous = current
        self._context, self._key, self._digest, self._result = context, key, digest, result
        return copy.deepcopy(result)

    def _measure(self, old, new, binding, result):
        ee_delta = new["ee"] - old["ee"]
        target_delta = new["target"] - old["target"]
        ee_motion, target_motion = float(np.linalg.norm(ee_delta)), float(np.linalg.norm(target_delta))
        residual = float(np.linalg.norm(target_delta - ee_delta))
        goal_motion = float(np.linalg.norm(new["goal"] - old["goal"]))
        distance = float(np.linalg.norm(new["target"] - new["ee"]))
        q1, q2 = old["quat"], new["quat"]
        norms = np.linalg.norm(q1) * np.linalg.norm(q2)
        rotation = float(2 * np.arccos(np.clip(abs(q1 @ q2) / norms, 0, 1))) if norms > 0 else None
        extent1 = old["target_bounds"][1] - old["target_bounds"][0]
        extent2 = new["target_bounds"][1] - new["target_bounds"][0]
        extent_change = float(np.max(np.abs(extent2 - extent1) / np.maximum(extent1, 0.005)))
        holding = dict(status="insufficient_evidence", reason=None, ee_motion_m=ee_motion,
            target_visible_centroid_motion_m=target_motion, relative_motion_residual_m=residual,
            goal_visible_centroid_motion_m=goal_motion, target_centroid_ee_distance_m=distance,
            gripper_aperture_m=new["aperture"], ee_rotation_rad=rotation,
            target_visible_extent_fraction_change=extent_change)
        if min(old["aperture"], new["aperture"]) < 0 or max(old["aperture"], new["aperture"]) > 0.025:
            holding["reason"] = "gripper_not_consistently_closed"
        elif ee_motion < 0.01:
            holding["reason"] = "insufficient_hand_motion"
        elif rotation is None or rotation > 0.05 or extent_change > 0.2 or goal_motion > 0.003 or distance > 0.12:
            holding["reason"] = "rotation_visibility_reference_or_proximity_insufficient"
        elif target_motion < 0.008 or residual > 0.003:
            holding.update(status="motion_not_consistent_with_holding", reason="target_does_not_follow_hand")
        else:
            self._following_intervals += 1
            holding.update(status="holding_motion_candidate" if self._following_intervals >= 2 else "insufficient_evidence",
                           reason="contact_not_verified" if self._following_intervals >= 2 else "need_another_following_interval")
        if holding["reason"] not in {"contact_not_verified", "need_another_following_interval"}:
            self._following_intervals = 0
        holding["consecutive_following_intervals"] = self._following_intervals
        result["holding"] = holding
        inside_xy = bool(np.all(new["target"][:2] >= new["goal_bounds"][0, :2])
                         and np.all(new["target"][:2] <= new["goal_bounds"][1, :2]))
        plausible_height = bool(new["target_bounds"][0, 2] >= new["goal_bounds"][0, 2] - 0.005
                                and new["target"][2] <= new["goal_bounds"][1, 2] + 0.12)
        stable = target_motion <= 0.003 and goal_motion <= 0.003
        eligible = (binding.goal_relation == "on" and inside_xy and plausible_height and stable
                    and new["aperture"] >= 0.04 and distance >= 0.08
                    and extent_change <= 0.2 and new["timestamp"] - old["timestamp"] >= 0.05)
        self._stable_goal_intervals = self._stable_goal_intervals + 1 if eligible else 0
        result["goal"] = dict(
            status="visible_goal_proximity_candidate" if self._stable_goal_intervals >= 2 else "insufficient_evidence",
            reason="support_contact_and_footprint_not_verified" if self._stable_goal_intervals >= 2 else "goal_proximity_stability_or_release_insufficient",
            target_centroid_inside_goal_visible_xy_bounds=inside_xy,
            visible_height_order_plausible=plausible_height, stable_visible_centroids=stable,
            consecutive_stable_goal_intervals=self._stable_goal_intervals)
