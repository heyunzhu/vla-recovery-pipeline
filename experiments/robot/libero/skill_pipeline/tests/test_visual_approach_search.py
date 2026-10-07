import copy
import unittest
from unittest.mock import patch
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_approach_search import approach_alternatives,compare_approaches
from experiments.robot.libero.skill_pipeline.tests.test_visual_pregrasp_control import frame


class ApproachSearchTest(unittest.TestCase):
    def sample(self):
        f=frame();start=f.robot_state['robot0_eef_pos'];goal=[.1,.1,1.1]
        return f,dict(episode_id=f.episode_id,env_step=f.env_step,camera_id=f.camera_id,
            goal_world_m=goal,waypoints_world_m=[start,[.1,.1,start[2]],goal],execution_allowed=False)

    def test_alternatives_preserve_goal_and_input(self):
        f,p=self.sample();before=copy.deepcopy(p);alternatives=approach_alternatives(f,p)
        self.assertEqual(len(alternatives),7);self.assertEqual(p,before)
        for candidate in alternatives:
            self.assertEqual(candidate['proposal']['goal_world_m'],p['goal_world_m'])
            self.assertEqual(candidate['proposal']['waypoints_world_m'][-1],p['goal_world_m'])
            self.assertFalse(candidate['proposal']['execution_allowed'])
            waypoints=np.array(candidate['proposal']['waypoints_world_m'])
            self.assertTrue(np.all(waypoints>=[-.5,-.5,1.0]) and np.all(waypoints<=[.4,.5,1.5]))

    def test_stale_and_changed_endpoint_rejected(self):
        f,p=self.sample();p['env_step']+=1
        with self.assertRaises(ValueError):approach_alternatives(f,p)
        f,p=self.sample();p['waypoints_world_m'][-1]=[0,0,1.1]
        with self.assertRaises(ValueError):approach_alternatives(f,p)

    def test_refused_ik_is_not_ranked_and_no_execution_authorized(self):
        f,p=self.sample()
        with patch('experiments.robot.libero.skill_pipeline.visual_approach_search.prepare_panda_joint_trajectory',return_value={'status':'refused'}):
            result,arrays=compare_approaches(f,p,'unused',None)
        self.assertEqual(result['ranking'],[]);self.assertEqual(arrays,{})
        self.assertFalse(result['execution_allowed']);self.assertFalse(result['ranking_certifies_safety'])

    def test_comparison_rejects_changed_baseline(self):
        f,p=self.sample();changes=dict(poses=[{'new_membership_count':0}],poses_with_new_memberships=0)
        with patch('experiments.robot.libero.skill_pipeline.visual_approach_search.prepare_panda_joint_trajectory',return_value={'status':'kinematic_candidate'}),patch(
            'experiments.robot.libero.skill_pipeline.visual_approach_search.inspect_collision_changes',side_effect=[
                (changes,{'baseline_memberships':np.array([[0,1]])}),
                (changes,{'baseline_memberships':np.array([[0,2]])})]):
            with self.assertRaisesRegex(ValueError,'baseline changed'):compare_approaches(f,p,'unused',None)


if __name__=='__main__':unittest.main()
