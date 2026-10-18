import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_rack_skill import resolve_observed_skill_surface


class VisualRackSkillTest(unittest.TestCase):
    def test_adapter_receives_observed_site_in_robot_frame_and_saved_parameters(self):
        plane=dict(id='plane_00',basis_world=np.eye(3).tolist(),origin_world_m=[1.,2.,3.],
                   uv_bounds_m=[[-.2,-.1],[.2,.1]])
        frame=np.eye(4);frame[:3,3]=[.5,1.,2.]
        hint=dict(geometry_profile='saved_profile',place_z_offset_m=.095,
                  source_site_name='simulation_site',source_object='simulation_object')
        def resolver(profile,**kwargs):
            self.assertEqual(profile,'saved_profile')
            self.assertEqual(kwargs['hint']['place_z_offset_m'],.095)
            obj=kwargs['scene'].objects['visual_goal'];site=obj.geometry['sites'][0]
            np.testing.assert_allclose(site['pos'],[.5,1.,1.])
            np.testing.assert_allclose(site['size'],[.2,.1,0.])
            self.assertEqual(kwargs['hint']['source_site_name'],'rgbd_observed_top_region')
            return dict(metadata={},center=site['pos'])
        result,audit=resolve_observed_skill_surface(resolver,hint,plane,frame,'visual_goal')
        self.assertFalse(result['metadata']['oracle_object_state_used'])
        self.assertEqual(hint['source_site_name'],'simulation_site')
        self.assertEqual(audit['observed_site_world']['source'],'current_RGBD_upper_plane')

    def test_unresolved_skill_does_not_fall_back_to_simulation_geometry(self):
        plane=dict(id='plane_00',basis_world=np.eye(3).tolist(),origin_world_m=[0.,0.,1.],
                   uv_bounds_m=[[-.2,-.1],[.2,.1]])
        with self.assertRaisesRegex(ValueError,'did not resolve'):
            resolve_observed_skill_surface(lambda *a,**k:None,dict(geometry_profile='missing'),
                                           plane,np.eye(4),'visual_goal')


if __name__=='__main__':unittest.main()
