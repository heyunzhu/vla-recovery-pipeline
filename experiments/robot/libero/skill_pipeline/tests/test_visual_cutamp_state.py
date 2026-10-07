import sys
import types
import unittest
from unittest.mock import patch
from experiments.robot.libero.tiptop_repro.visual_cutamp_state import build_observed_initial_state
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackendConfig,_build_simulator_truth_initial_state


class FakeFluent:
    def __init__(self,name):self.name=name
    def ground(self,*args):return self.name,tuple(args)


class VisualCuTAMPStateTest(unittest.TestCase):
    def sample(self):
        env=types.SimpleNamespace(type_to_objects={'Movable':['obj_001'],'Surface':['obj_002']})
        atom=dict(predicate='handempty',args=[],source='rgbd_temporal_gripper',snapshot_id='episode:step1:agentview',confidence=.9)
        problem=types.SimpleNamespace(q_init_debug={'rgbd_snapshot_id':atom['snapshot_id']},init_atoms=[atom])
        domain=types.ModuleType('cutamp.tamp_domain')
        domain.all_tamp_fluents=[FakeFluent(n) for n in ['HandEmpty','On','At','CanMove','IsMovable','HasNotPickedUp','IsSurface']]
        domain.get_initial_state=lambda **kwargs:(_ for _ in ()).throw(AssertionError('default state must not be consumed'))
        return env,problem,{'obj_001':'obj_001','obj_002':'obj_002'},RealCuTAMPBackendConfig(initial_state_source='rgbd_observed'),domain

    def test_observed_mode_reaches_existing_backend_without_default_state(self):
        env,p,n,c,d=self.sample()
        with patch.dict(sys.modules,{'cutamp':types.ModuleType('cutamp'),'cutamp.tamp_domain':d}):
            state,debug,reason=_build_simulator_truth_initial_state(env,p,n,c)
        self.assertIsNone(reason);self.assertIn(('HandEmpty',()),state)
        self.assertFalse(debug['default_initial_state_used'])
        self.assertEqual(debug['initial_state_source'],'rgbd_observed_only')

    def test_unknown_hand_state_has_no_default_handempty(self):
        env,p,n,c,d=self.sample();p.init_atoms=[]
        with patch.dict(sys.modules,{'cutamp.tamp_domain':d}):state,debug,reason=build_observed_initial_state(env,p,n,c)
        self.assertEqual(state,frozenset());self.assertEqual(reason,'visual_hand_state_unknown')

    def test_oracle_sources_and_stale_snapshot_are_rejected(self):
        for key,value in [('source','simulator_truth'),('snapshot_id','episode:step0:agentview')]:
            env,p,n,c,d=self.sample();p.init_atoms[0][key]=value
            with patch.dict(sys.modules,{'cutamp.tamp_domain':d}):state,debug,reason=build_observed_initial_state(env,p,n,c)
            self.assertEqual(state,frozenset());self.assertEqual(reason,'rgbd_initial_atom_provenance_mismatch')

    def test_low_confidence_is_unknown_not_handempty(self):
        env,p,n,c,d=self.sample();p.init_atoms[0]['confidence']=.1
        with patch.dict(sys.modules,{'cutamp.tamp_domain':d}):state,debug,reason=build_observed_initial_state(env,p,n,c)
        self.assertEqual(reason,'visual_hand_state_unknown');self.assertEqual(len(debug['dropped_fluents']),1)

    def test_on_fact_uses_explicit_observed_roles(self):
        env,p,n,c,d=self.sample();p.init_atoms.append(dict(p.init_atoms[0],predicate='on',args=['obj_001','obj_002']))
        with patch.dict(sys.modules,{'cutamp.tamp_domain':d}):state,debug,reason=build_observed_initial_state(env,p,n,c)
        self.assertIsNone(reason);self.assertIn(('On',('obj_001','obj_002')),state)
        p.init_atoms[-1]['args'].reverse()
        with patch.dict(sys.modules,{'cutamp.tamp_domain':d}):state,debug,reason=build_observed_initial_state(env,p,n,c)
        self.assertEqual(reason,'invalid_rgbd_on_roles')

    def test_initial_holding_remains_explicitly_unsupported(self):
        env,p,n,c,d=self.sample();p.init_atoms[0].update(predicate='holding',args=['obj_001'])
        with patch.dict(sys.modules,{'cutamp.tamp_domain':d}):state,debug,reason=build_observed_initial_state(env,p,n,c)
        self.assertEqual(reason,'visual_initial_holding_not_yet_supported');self.assertEqual(state,frozenset())


if __name__=='__main__':unittest.main()
