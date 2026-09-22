"""Experimental cuRobo motion adapter; imports GPU dependencies only on use.

Uses the v0.7.x MotionGen interface and cuTAMP's Panda configuration. Runtime
API mismatches fail closed. Bounding boxes are conservative, not mesh-accurate.
"""
from __future__ import annotations

import numpy as np

from .articulation import ArticulationError
from .articulation_collision import boxes_from_problem, boxes_overlap, sphere_clearance


class CuroboArticulationMotion:
    def __init__(self, problem, part, robot):
        import torch
        from curobo.geom.types import Cuboid, WorldConfig
        from curobo.types.base import TensorDeviceType
        from curobo.types.math import Pose
        from curobo.types.state import JointState
        from curobo.wrap.reacher.motion_gen import MotionGen, MotionGenConfig, MotionGenPlanConfig
        from cutamp.robots.franka import franka_curobo_cfg

        if robot != "panda" or not torch.cuda.is_available():
            raise ArticulationError("articulation_requires_panda_and_cuda")
        self.Pose, self.JointState = Pose, JointState
        self.Cuboid, self.WorldConfig = Cuboid, WorldConfig
        self.PlanConfig = MotionGenPlanConfig
        self.tensor = TensorDeviceType()
        self.part = part
        self.reference_boxes = boxes_from_problem(problem)
        ids = {box.geom_id for box in self.reference_boxes}
        if not set(part.moving_geom_ids) <= ids:
            raise ArticulationError("articulation_collision_geometry_incomplete")
        self.allowed_pairs = set()
        for pair in problem.articulation_options.get("allowed_environment_contacts", []):
            if len(pair) != 2 or pair[0] == pair[1] or not set(pair) <= ids:
                raise ArticulationError("invalid_environment_contact_pair")
            if len(set(pair) & set(part.moving_geom_ids)) != 1:
                raise ArticulationError("contact_pair_must_join_moving_and_fixed_geometry")
            self.allowed_pairs.add(frozenset(pair))
        self.position = None
        self.set_position(part.reference_position)
        self.motion = MotionGen(MotionGenConfig.load_from_robot_config(
            robot_cfg=franka_curobo_cfg(), world_model=self._world(),
            use_cuda_graph=False, collision_activation_distance=0.0,
        ))
        kin = self.motion.kinematics.kinematics_config
        links = problem.articulation_options.get("contact_links", ["panda_leftfinger", "panda_rightfinger"])
        # Explicitly forbid widening the exception to wrist/arm links.
        if not links or any(link not in {"panda_leftfinger", "panda_rightfinger"} for link in links):
            raise ArticulationError("only_finger_handle_contact_is_supported")
        self.finger_indices = set()
        for link in links:
            self.finger_indices.update(kin.get_sphere_index_from_link_name(link).cpu().tolist())
        if not self.finger_indices:
            raise ArticulationError("finger_collision_spheres_unavailable")

    def _world(self):
        from .libero_panda_frames import matrix_to_quat_wxyz
        # Handle collision is evaluated below with a finger-only pair mask.
        # It is never exempted for the robot's wrist or arm.
        boxes = [box for box in self.boxes if box.geom_id not in self.part.handle_geom_ids]
        return self.WorldConfig(cuboid=[self.Cuboid(
            name=b.name, pose=[*b.pose[:3, 3], *matrix_to_quat_wxyz(b.pose[:3, :3])],
            dims=(b.half_extents * 2).tolist(),
        ) for b in boxes])

    def set_position(self, position):
        if self.position == position:
            return
        displacement = self.part.displacement(position)
        self.boxes = [b.moved(displacement) if b.geom_id in self.part.moving_geom_ids else b
                      for b in self.reference_boxes]
        self.position = position
        if hasattr(self, "motion"):
            self.motion.update_world(self._world())

    def _state(self, q):
        return self.JointState.from_position(self.tensor.to_device(np.asarray(q))[None])

    def fk(self, q):
        state = self.motion.compute_kinematics(self._state(q))
        return state.ee_pose.get_matrix()[0].detach().cpu().numpy()

    def ik(self, pose, seed):
        target = self.Pose.from_matrix(self.tensor.to_device(pose)[None])
        seed_tensor = self.tensor.to_device(seed)[None]
        result = self.motion.solve_ik(target, seed_config=seed_tensor[:, None], retract_config=seed_tensor)
        if not bool(result.success.all().item()):
            return None
        return result.solution.reshape(-1, len(seed))[0].detach().cpu().numpy()

    def valid(self, q, position, contact):
        self.set_position(position)
        metrics = self.motion.check_constraints(self._state(q))
        if not bool(metrics.feasible.all().item()):
            return False
        state = self.motion.compute_kinematics(self._state(q))
        spheres_tensor = getattr(state, "robot_spheres", None)
        if spheres_tensor is None:
            raise ArticulationError("curobo_robot_spheres_unavailable")
        spheres = spheres_tensor.reshape(-1, 4).detach().cpu().numpy()
        if not np.isfinite(spheres).all():
            return False
        for box in self.boxes:
            if box.geom_id not in self.part.handle_geom_ids:
                continue
            colliding = np.flatnonzero((sphere_clearance(spheres, box) < -1e-5) & (spheres[:, 3] > 0))
            if any(not contact or int(i) not in self.finger_indices for i in colliding):
                return False
        moving = [b for b in self.boxes if b.geom_id in self.part.moving_geom_ids]
        fixed = [b for b in self.boxes if b.geom_id not in self.part.moving_geom_ids]
        for a in moving:
            for b in fixed:
                if frozenset((a.geom_id, b.geom_id)) not in self.allowed_pairs and boxes_overlap(a, b):
                    return False
        return True

    def _plan(self, q, target, position):
        self.set_position(position)
        result = self.motion.plan_single(
            self._state(q), self.Pose.from_matrix(self.tensor.to_device(target)[None]),
            self.PlanConfig(timeout=2.0, enable_finetune_trajopt=False),
        )
        if not bool(result.success.all().item()):
            raise ArticulationError(f"curobo_free_motion_failed:{result.status}")
        path = result.get_interpolated_plan().position.detach().cpu().numpy()
        # Preserve the actual start explicitly for endpoint/interpolation checks.
        return np.vstack([q, path])

    def approach(self, q, target, position):
        pre = target.copy()
        pre[:3, 3] -= target[:3, 2] * 0.05
        first = self._plan(q, pre, position)
        return np.vstack([first, self._plan(first[-1], target, position)[1:]])

    def retreat(self, q, position):
        target = self.fk(q)
        target[:3, 3] -= target[:3, 2] * 0.05
        return self._plan(q, target, position)
