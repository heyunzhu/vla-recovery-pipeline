import subprocess
import sys
import unittest
import numpy as np
from experiments.robot.libero.tiptop_repro.scene_types import ObjectState,JointState,SceneState


class PlannerImportBoundaryTest(unittest.TestCase):
    def test_real_backend_loads_under_oracle_guard_in_fresh_process(self):
        code='''
import sys
from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard,FORBIDDEN_MODULES
with OracleImportGuard() as guard:
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackend,RealCuTAMPBackendConfig
    from experiments.robot.libero.tiptop_repro.tamp_scene import TAMPProblem,TAMPObject,GroundedAtom
    assert guard.blocked_import_attempts==0
    assert not any(name in sys.modules for name in FORBIDDEN_MODULES)
    print('real_backend_import_without_oracle')
'''
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('real_backend_import_without_oracle',result.stdout)

    def test_oracle_reader_reexports_same_classes(self):
        code='''
from experiments.robot.libero.tiptop_repro import scene_reader,scene_types
assert scene_reader.SceneState is scene_types.SceneState
assert scene_reader.ObjectState is scene_types.ObjectState
assert scene_reader.JointState is scene_types.JointState
assert callable(scene_reader.read_scene)
'''
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_legacy_fields_helpers_and_default_factories_preserved(self):
        def scene():return SceneState(np.array([0,0,0]),np.array([1,0,0,0]),np.array([.04,-.04]))
        first=scene();second=scene()
        first.objects['near']=ObjectState('near',np.array([.01,0,0]))
        first.objects['far']=ObjectState('far',np.array([1,0,0]))
        first.contacts.append({'legacy':True})
        self.assertEqual(first.nearest_object().name,'near')
        self.assertTrue(first.gripper_open)
        self.assertEqual(second.objects,{})
        self.assertEqual(second.contacts,[])
        self.assertEqual(second.holding_evidence,{})
        self.assertEqual(JointState('joint',.1).qvel,0)


if __name__=='__main__':unittest.main()
