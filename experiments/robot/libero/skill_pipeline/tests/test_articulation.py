from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from experiments.robot.libero.tiptop_repro.articulation import (
    ArticulatedPart, ArticulationError, PathSettings, bind_articulations,
    pose_residual, read_articulation_structure, refine_articulation,
)
from experiments.robot.libero.tiptop_repro.articulation_collision import CollisionBox, boxes_overlap, sphere_clearance
from experiments.robot.libero.tiptop_repro.articulation_executor import execute_articulated_plan
from experiments.robot.libero.tiptop_repro.cutamp_articulation import skeletons, solve
from experiments.robot.libero.tiptop_repro.cutamp_fluents import map_atom_to_cutamp
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    RealCuTAMPBackend, RealCuTAMPBackendConfig, _problem_from_dict, _problem_to_dict,
)
from experiments.robot.libero.tiptop_repro.scene_reader import JointState
from experiments.robot.libero.tiptop_repro.tamp_scene import GroundedAtom, TAMPProblem


def part(**changes):
    values = dict(
        part_id="drawer", joint_name="slide0", joint_type="slide", body_name="drawer_body",
        frame="robot_base", axis=[1., 0., 0.], anchor=[0., 0., 0.], reference_position=0.,
        joint_range=[0., 0.2], handle_reference=np.eye(4).tolist(), open_range=[0.15, 0.2],
        closed_range=[0., 0.02], target_source="test_fixture", handle_site="handle_site",
        moving_geom_ids=[1, 2], handle_geom_ids=[2], grasps=[np.eye(4).tolist()],
    )
    values.update(changes)
    return ArticulatedPart(**values)


class LinearMotion:
    def set_position(self, s):
        self.position = s

    def fk(self, q):
        pose = np.eye(4)
        pose[0, 3] = q[0]
        return pose

    def ik(self, pose, seed):
        return np.array([pose[0, 3]])

    def valid(self, q, s, contact):
        return bool(np.isfinite(q).all() and 0 <= s <= 0.2)

    def approach(self, q, pose, s):
        return np.array([q, [pose[0, 3]]])

    def retreat(self, q, s):
        return np.array([q, q - 0.01])


class ModelTests(unittest.TestCase):
    def test_slide_uses_reference_not_zero(self):
        p = part(reference_position=0.1)
        self.assertAlmostEqual(p.handle_pose(0.15)[0, 3], 0.05)

    def test_hinge_position_and_orientation(self):
        ref = np.eye(4)
        ref[0, 3] = 1
        p = part(joint_type="hinge", joint_range=[0, 2], open_range=[1, 2], axis=[0, 0, 1],
                 handle_reference=ref.tolist())
        pose = p.handle_pose(np.pi / 2)
        np.testing.assert_allclose(pose[:3, 3], [0, 1, 0], atol=1e-7)
        np.testing.assert_allclose(pose[:3, 0], [0, 1, 0], atol=1e-7)

    def test_world_frame_conversion_commutes(self):
        p = part(joint_type="hinge", joint_range=[0, 2], open_range=[1, 2], axis=[0, 0, 1])
        frame = np.array([[0, -1, 0, 2], [1, 0, 0, 3], [0, 0, 1, 4], [0, 0, 0, 1.]])
        converted = p.in_frame(frame, "world")
        np.testing.assert_allclose(converted.handle_pose(0.4), frame @ p.handle_pose(0.4))

    def test_half_open_is_neither_open_nor_closed(self):
        self.assertEqual(part().mode(0.08), "intermediate")

    def test_negative_direction(self):
        p = part(reference_position=0, joint_range=[-0.2, 0], open_range=[-0.2, -0.15], closed_range=[-0.02, 0])
        self.assertEqual(p.mode(-0.18), "open")
        self.assertLess(p.handle_pose(-0.18)[0, 3], 0)

    def test_invalid_models_fail_closed(self):
        for kwargs in (dict(axis=[0, 0, 0]), dict(open_range=[0.1, 0.4]), dict(open_range=[0.01, 0.1]),
                       dict(reference_position=float("nan")), dict(grasps=[]), dict(handle_geom_ids=[99])):
            with self.subTest(kwargs=kwargs), self.assertRaises(ArticulationError):
                part(**kwargs)

    def test_out_of_range_position(self):
        with self.assertRaises(ArticulationError):
            part().handle_pose(0.3)

    def test_exact_binding_required(self):
        with self.assertRaisesRegex(ArticulationError, "invalid_articulation_binding"):
            bind_articulations({}, [{"joint_name": "drawer"}])

    def test_settings_require_positive_finite_numbers(self):
        with self.assertRaises(ArticulationError):
            PathSettings(slide_step=0)

    def test_read_exact_mujoco_body_joint_relationship(self):
        model = SimpleNamespace(
            joint_names=["drawer_joint"], jnt_type=[2], jnt_bodyid=[1], body_jntnum=[0, 1, 0],
            body_parentid=[0, 0, 1], jnt_limited=[1], nbody=3, ngeom=2, geom_bodyid=[1, 2],
            geom_contype=[1, 1], geom_conaffinity=[1, 1], site_names=["handle_site"], site_bodyid=[2],
            body_names=["world", "drawer_body", "handle_body"], jnt_qposadr=[0], jnt_range=[[0, .2]],
            geom_names=["drawer_geom", "handle_geom"],
        )
        data = SimpleNamespace(site_xmat=[np.eye(3)], site_xpos=[[0, 0, 0]],
                               geom_xmat=[np.eye(3), np.eye(3)], geom_xpos=[[0, 0, 0], [0, 0, 0]],
                               xaxis=[[1, 0, 0]], xanchor=[[0, 0, 0]], qpos=[.03])
        raw = read_articulation_structure(model, data)
        self.assertEqual(raw["drawer_joint"]["moving_geom_ids"], [0, 1])
        binding = dict(part_id="drawer", joint_name="drawer_joint", handle_site="handle_site",
                       handle_geoms=["handle_geom"], open_range=[.15, .2], closed_range=[0, .02],
                       target_source="test", grasps=[np.eye(4).tolist()])
        self.assertEqual(bind_articulations(raw, [binding])["drawer"].reference_position, .03)
        site_only_binding = dict(binding)
        site_only_binding.pop("handle_geoms")
        site_only = bind_articulations(raw, [site_only_binding])["drawer"]
        self.assertEqual(site_only.handle_geom_ids, site_only.moving_geom_ids)
        with self.assertRaisesRegex(ArticulationError, "duplicate"):
            bind_articulations(raw, [binding, binding])
        model.body_jntnum[2] = 1
        # A nested joint's child is not incorrectly assigned to the parent.
        self.assertEqual(read_articulation_structure(model, data)["drawer_joint"]["moving_geom_ids"], [0])


class ConstraintTests(unittest.TestCase):
    def test_refine_slide(self):
        result = refine_articulation(part(), "open", np.eye(4), [0], LinearMotion())
        self.assertAlmostEqual(result["joint_positions"][-1], .175)
        self.assertEqual(len(result["positions"]), len(result["joint_positions"]))
        self.assertLess(result["max_position_error"], 1e-6)

    def test_wrong_initial_grasp_rejected(self):
        with self.assertRaisesRegex(ArticulationError, "handle_pose"):
            refine_articulation(part(), "open", np.eye(4), [.05], LinearMotion())

    def test_no_ik_rejected(self):
        motion = LinearMotion()
        motion.ik = lambda *_: None
        with self.assertRaisesRegex(ArticulationError, "ik_failed"):
            refine_articulation(part(), "open", np.eye(4), [0], motion)

    def test_intermediate_collision_rejected(self):
        motion = LinearMotion()
        motion.valid = lambda q, s, contact: not .002 < s < .003
        with self.assertRaisesRegex(ArticulationError, "collision"):
            refine_articulation(part(), "open", np.eye(4), [0], motion)

    def test_interpolated_grasp_error_rejected(self):
        motion = LinearMotion()
        base_fk = motion.fk
        motion.fk = lambda q: base_fk(np.asarray(q) ** 2)
        motion.ik = lambda pose, seed: np.sqrt([pose[0, 3]])
        with self.assertRaisesRegex(ArticulationError, "handle_pose"):
            refine_articulation(part(), "open", np.eye(4), [0], motion,
                                PathSettings(slide_step=.2, max_joint_jump=1, joint_step=1))

    def test_missing_collision_check_never_defaults_to_valid(self):
        with self.assertRaises(AttributeError):
            refine_articulation(part(), "open", np.eye(4), [0], SimpleNamespace(fk=LinearMotion().fk))

    def test_box_collision_and_finger_distance(self):
        box = CollisionBox("a", 1, np.eye(4), np.ones(3))
        other_pose = np.eye(4)
        other_pose[0, 3] = 2.1
        other = CollisionBox("b", 2, other_pose, np.ones(3))
        self.assertFalse(boxes_overlap(box, other))
        other.pose[0, 3] = 1.9
        self.assertTrue(boxes_overlap(box, other))
        np.testing.assert_allclose(sphere_clearance([[2, 0, 0, .2]], box), [.8])


@unittest.skipUnless(importlib.util.find_spec("cutamp") is not None, "requires actual cuTAMP source on PYTHONPATH")
class NativeDomainTests(unittest.TestCase):
    def test_search_produces_native_operators_and_constraints(self):
        skeleton = next(iter(skeletons(part(), "open")))
        self.assertEqual([op.operator.name for op in skeleton],
                         ["GraspHandle", "OpenArticulatedFromClosed", "ReleaseHandle"])
        self.assertIn("ArticulationTarget", [type(c).__name__ for c in skeleton[1].constraints])

    def test_half_open_can_close(self):
        skeleton = next(iter(skeletons(part(reference_position=.1), "closed")))
        self.assertEqual(skeleton[1].operator.name, "CloseArticulatedFromIntermediate")

    def test_already_satisfied_has_empty_skeleton(self):
        self.assertEqual(next(iter(skeletons(part(reference_position=.18), "open"))), [])

    def test_native_search_to_refined_plan(self):
        result = solve(part(), "open", [-.05], LinearMotion())
        self.assertEqual([a["phase"] for a in result["actions"]],
                         ["approach", "grasp", "articulate", "release", "retreat"])

    def test_no_fallback_when_collision_blocks_all_candidates(self):
        motion = LinearMotion()
        motion.valid = lambda *_: False
        with self.assertRaisesRegex(ArticulationError, "no_feasible"):
            solve(part(), "open", [-.05], motion)


class IntegrationTests(unittest.TestCase):
    def problem(self):
        return TAMPProblem(movables=[], surfaces=[], statics=[], goal_atoms=[GroundedAtom("open", ("drawer",))],
                           init_atoms=[{"predicate": "handempty", "args": []}],
                           articulations={"drawer": part().to_dict()}, articulation_options={"enabled": True}, q_init=[0])

    def test_problem_roundtrip(self):
        p = self.problem()
        restored = _problem_from_dict(_problem_to_dict(p))
        self.assertEqual(restored.articulations, p.articulations)
        self.assertEqual(restored.articulation_options, p.articulation_options)

    def test_open_not_silently_discarded(self):
        result = map_atom_to_cutamp({"predicate": "open", "args": ["drawer"]})
        self.assertEqual(result.fluents[0].predicate, "open")

    def test_default_disabled(self):
        p = self.problem()
        p.articulation_options = {}
        result = RealCuTAMPBackend().solve(p)
        self.assertFalse(result.feasible)
        self.assertIn("disabled", result.failure_reason)

    def test_missing_binding(self):
        p = self.problem()
        p.articulations.clear()
        result = RealCuTAMPBackend().solve(p)
        self.assertIn("invalid_articulation_binding", result.failure_reason)

    def test_mixed_goal_rejected(self):
        p = self.problem()
        p.goal_atoms.append(GroundedAtom("on", ("cup", "table")))
        result = RealCuTAMPBackend().solve(p)
        self.assertIn("unsupported_mixed", result.failure_reason)

    def test_handempty_requires_evidence(self):
        p = self.problem()
        p.init_atoms = []
        result = RealCuTAMPBackend().solve(p)
        self.assertIn("handempty_unconfirmed", result.failure_reason)

    def test_occupied_hand_rejected(self):
        p = self.problem()
        p.current_grasp = {"object_name": "cup"}
        self.assertIn("requires_handempty", RealCuTAMPBackend().solve(p).failure_reason)

    def test_executor_does_not_accept_empty_plan(self):
        client = SimpleNamespace(num_env_steps=0, get_scene=lambda: SimpleNamespace(joints={"slide0": JointState("slide0", 0)}))
        result = execute_articulated_plan(client, {"part": part().to_dict(), "goal": "open", "actions": []}, 10)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "empty_articulation_plan")

    def test_executor_rejects_stale_plan(self):
        client = SimpleNamespace(num_env_steps=0, get_scene=lambda: SimpleNamespace(joints={"slide0": JointState("slide0", .1)}))
        result = execute_articulated_plan(client, {"part": part().to_dict(), "goal": "open", "actions": []}, 10)
        self.assertEqual(result["error"], "stale_articulation_plan")

    def test_executor_already_satisfied_uses_real_joint(self):
        p = part(reference_position=.18)
        client = SimpleNamespace(num_env_steps=0, get_scene=lambda: SimpleNamespace(
            joints={"slide0": JointState("slide0", .18)}, gripper_open=True))
        result = execute_articulated_plan(client, {"part": p.to_dict(), "goal": "open", "actions": [],
                                                   "already_satisfied": True}, 10)
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
