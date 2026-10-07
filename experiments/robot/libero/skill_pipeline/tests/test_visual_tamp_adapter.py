import copy
import dataclasses
import sys
import types
import unittest
from unittest.mock import patch
import numpy as np

from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample, LANGUAGE
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from experiments.robot.libero.skill_pipeline.visual_planning_input import build_visual_planning_input
from experiments.robot.libero.skill_pipeline.visual_tamp_adapter import build_visual_tamp_problem, voxel_boxes
from experiments.robot.libero.tiptop_repro.visual_cutamp_world import build_visual_world
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackend, RealCuTAMPBackendConfig
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import _problem_from_dict


def sample():
    frame,detections,_=_sample()
    state=dict(frame.robot_state,robot0_joint_pos=[0,-.7,0,-2.2,0,1.6,.7])
    frame=dataclasses.replace(frame,robot_state=state)
    provider=RGBDSceneProvider(lambda _:detections,detector_id='test',camera_id=frame.camera_id)
    handoff=VisualDryRunAdapter(provider).query_state(frame,LANGUAGE)
    return frame,build_visual_planning_input(frame,handoff,provider)


class VisualTAMPAdapterTest(unittest.TestCase):
    def test_visual_serialization_round_trip(self):
        frame,evidence=sample();p=build_visual_tamp_problem(frame,evidence).problem
        self.assertEqual(_problem_from_dict(p.to_dict()).to_dict(),p.to_dict())

    def test_runner_overrides_inherited_collision_escape(self):
        frame,evidence=sample();p=build_visual_tamp_problem(frame,evidence).problem
        cfg=RealCuTAMPBackendConfig(initial_state_source='rgbd_observed',runner_python='unused')
        with patch.dict('os.environ',{'CUTAMP_ALLOW_START_COLLISION_ESCAPE':'1','CUTAMP_CONTACT_MODE_TARGET':'1'}):
            with patch('experiments.robot.libero.tiptop_repro.real_cutamp_backend.subprocess.run',
                       return_value=types.SimpleNamespace(returncode=1,stdout='',stderr='probe')) as run:
                RealCuTAMPBackend(cfg)._solve_with_runner(p)
        env=run.call_args.kwargs['env']
        for key in ('CUTAMP_ALLOW_START_COLLISION_ESCAPE','CUTAMP_CONTACT_MODE_TARGET','CUTAMP_START_ESCAPE_Z'):
            self.assertEqual(env[key],'0')

    def test_measured_roles_and_unknown_initial_facts(self):
        frame,evidence=sample()
        result=build_visual_tamp_problem(frame,evidence)
        p=result.problem
        self.assertEqual([p.movables[0].name,p.surfaces[0].name],evidence.report['desired_goal']['args'])
        self.assertEqual(p.init_atoms,[])
        self.assertEqual(p.q_init,frame.robot_state['robot0_joint_pos'])
        self.assertFalse(result.report['execution_allowed'])
        self.assertFalse(result.report['solver_initial_state_ready'])
        transform=np.linalg.inv(p.q_init_debug['world_from_base_candidate'])
        for surface in evidence.report['surfaces']:
            obj=next(o for o in p.movables+p.surfaces if o.name==surface['visual_id'])
            points=evidence.arrays[surface['array_key']] @ transform[:3,:3].T+transform[:3,3]
            np.testing.assert_allclose(obj.pos,(points.min(0)+points.max(0))/2)
            np.testing.assert_allclose(obj.half_extents,(points.max(0)-points.min(0))/2+.003)
            self.assertIsNone(obj.mesh_path)

    def test_changed_depth_rejected(self):
        frame,evidence=sample()
        depth=frame.depth_m.copy();depth[0,0]+=.01
        with self.assertRaisesRegex(ValueError,'snapshot mismatch'):
            build_visual_tamp_problem(dataclasses.replace(frame,depth_m=depth),evidence)

    def test_injected_points_and_duplicate_ids_rejected(self):
        frame,evidence=sample()
        arrays=dict(evidence.arrays);arrays['observed_world_points']=np.array([[123.,456.,789.]])
        with self.assertRaisesRegex(ValueError,'current depth'):
            build_visual_tamp_problem(frame,dataclasses.replace(evidence,arrays=arrays))
        report=copy.deepcopy(evidence.report);report['surfaces'].append(report['surfaces'][0])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            build_visual_tamp_problem(frame,dataclasses.replace(evidence,report=report))

    def test_all_voxels_cover_points_or_explicitly_fail_budget(self):
        points=np.array([[-.011,0,0],[.011,0,0],[.012,0,0]])
        centres=voxel_boxes(points,.02)
        self.assertEqual(len(centres),2)
        for point in points:self.assertTrue(np.any(np.all(np.abs(centres-point)<=.01,axis=1)))
        with self.assertRaisesRegex(ValueError,'cannot drop'):
            voxel_boxes(points,.02,max_voxels=1)

    def test_native_world_preserves_support_and_explicit_dimensions(self):
        frame,evidence=sample();p=build_visual_tamp_problem(frame,evidence).problem
        class Box:
            def __init__(self,**kw):self.__dict__.update(kw)
        fluent=types.SimpleNamespace(name='On',ground=lambda *args:('on',*args))
        modules={
            'curobo.geom.types':types.SimpleNamespace(Cuboid=Box),
            'cutamp.envs':types.SimpleNamespace(TAMPEnvironment=Box),
            'cutamp.tamp_domain':types.SimpleNamespace(all_tamp_fluents=[fluent])}
        with patch.dict(sys.modules,modules):
            env,names,notes,debug=build_visual_world(p)
            self.assertIn(p.surfaces[0].name,[o.name for o in env.statics])
            self.assertEqual(len(env.statics),len(p.statics)+len(p.surfaces))
            np.testing.assert_allclose(env.movables[0].dims,np.asarray(p.movables[0].half_extents)*2)
            self.assertFalse(debug['default_table_added'])
            self.assertFalse(debug['goal_surface_collision_excluded'])
            backend=RealCuTAMPBackend(RealCuTAMPBackendConfig(initial_state_source='rgbd_observed'))
            with patch('experiments.robot.libero.tiptop_repro.real_cutamp_backend._cuboid_dims',side_effect=AssertionError('legacy branch used')):
                self.assertEqual(backend._build_env(p)[1],names)
            p.movables[0].geometry['collision_parts']=[]
            with self.assertRaisesRegex(ValueError,'unapproved'):
                build_visual_world(p)


if __name__=='__main__':unittest.main()
