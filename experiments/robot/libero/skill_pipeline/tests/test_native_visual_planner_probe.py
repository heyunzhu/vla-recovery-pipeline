import unittest
from unittest.mock import patch
from scripts.recovery.skill_pipeline.probe_native_visual_planner import validate_inputs,check_unused_gpu


class NativeProbeGateTest(unittest.TestCase):
    def sample(self):
        payload=dict(config=dict(initial_state_source='rgbd_observed',curobo_plan=True,
            serialize_trajectories=True,apply_simulator_truth_initial_state=False,
            enable_initial_holding_prebinding=False,accept_optimized_plan_if_motiongen_fails=False,
            project_motiongen_start_joint_limits=False,runner_python='',num_particles=128,num_opt_steps=60,max_loop_dur=30),
            problem=dict(q_init_debug=dict(rgbd_snapshot_id='current')))
        cpu=dict(status='native_visual_world_constructed',problem_sha256='sha',initial_state_blocker=None,
            initial_state_size=6,blocked_oracle_import_attempts=0,cuda_initialized=False,snapshot_id='current')
        return payload,cpu

    def test_matching_cpu_input_and_strict_config(self):
        p,c=self.sample();validate_inputs(p,c,'sha')
        for key,value in [('problem_sha256','stale'),('initial_state_blocker','unknown'),('cuda_initialized',True),('initial_state_size',0)]:
            altered=dict(c,**{key:value})
            with self.assertRaisesRegex(ValueError,'matching successful CPU'):validate_inputs(p,altered,'sha')

    def test_oracle_fallback_flags_and_changed_snapshot_rejected(self):
        for key in ('apply_simulator_truth_initial_state','enable_initial_holding_prebinding',
                    'accept_optimized_plan_if_motiongen_fails','project_motiongen_start_joint_limits'):
            p,c=self.sample();p['config'][key]=True
            with self.assertRaisesRegex(ValueError,'strict visual'):validate_inputs(p,c,'sha')
        p,c=self.sample();c['snapshot_id']='stale'
        with self.assertRaisesRegex(ValueError,'snapshot'):validate_inputs(p,c,'sha')

    def test_fresh_unused_gpu_check_and_occupied_cards(self):
        with patch('scripts.recovery.skill_pipeline.probe_native_visual_planner.subprocess.check_output',
                   side_effect=['6, GPU-test, 16, 0','']):
            self.assertEqual(check_unused_gpu(6)['uuid'],'GPU-test')
        for status,process in [('6, GPU-test, 1024, 0',''),('6, GPU-test, 16, 10',''),
                               ('6, GPU-test, 16, 0','GPU-test, 123')]:
            with patch('scripts.recovery.skill_pipeline.probe_native_visual_planner.subprocess.check_output',
                       side_effect=[status,process]):
                with self.assertRaisesRegex(RuntimeError,'occupied'):check_unused_gpu(6)


if __name__=='__main__':unittest.main()
