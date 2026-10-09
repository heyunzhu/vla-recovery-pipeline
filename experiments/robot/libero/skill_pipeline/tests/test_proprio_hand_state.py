import unittest
from experiments.robot.libero.skill_pipeline.proprio_hand_state import infer_panda_hand_state


class ProprioHandStateTest(unittest.TestCase):
    def test_signed_open_and_closed_ambiguity(self):
        opened = infer_panda_hand_state({'robot0_gripper_qpos': [.039, -.039]})
        self.assertEqual(opened['initial_atoms'][0]['predicate'], 'handempty')
        self.assertFalse(opened['holding_verified'])
        for q in ([.0, -.0], [.034, -.039], [.039, -.01]):
            result = infer_panda_hand_state({'robot0_gripper_qpos': q})
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(result['initial_atoms'], [])

    def test_invalid_sensor_state_rejected(self):
        for q in ([], [.04], [.04, .04], [float('nan'), -.04], [.08, -.04]):
            with self.assertRaises(ValueError):
                infer_panda_hand_state({'robot0_gripper_qpos': q})
