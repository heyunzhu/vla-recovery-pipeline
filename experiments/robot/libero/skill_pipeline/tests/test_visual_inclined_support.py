import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_inclined_support import canonical_box,support_candidates,observed_place_check
from experiments.robot.libero.skill_pipeline.tests import test_visual_observed_geometry as observed_tests
from experiments.robot.libero.skill_pipeline.visual_observed_geometry import fit_observed_cuboid

class InclinedSupportTest(unittest.TestCase):
    def test_box_canonical_axes_preserve_shape(self):
        points,_,_,_=observed_tests.ObservedGeometryTest.box_surface()
        old=fit_observed_cuboid(points);new=canonical_box(old)
        from scipy.spatial import cKDTree
        self.assertLess(cKDTree(old['corners_world_m']).query(new['corners_world_m'])[0].max(),1e-8)
        self.assertGreater(np.linalg.det(new['rotation_world_from_object']),.999)

    def test_sloped_candidates_preserve_footprint_and_clearance(self):
        x,y=np.meshgrid(np.arange(-.1,.101,.002),np.arange(-.07,.071,.002))
        points=np.c_[x.ravel(),y.ravel(),1+np.tan(np.pi/6)*y.ravel()]
        target=dict(collision_half_extents_m=[.04,.02,.01])
        surfaces=support_candidates(points,target)
        self.assertEqual(len(surfaces),1)
        self.assertAlmostEqual(surfaces[0]['tilt_degrees'],30,places=3)
        for c in surfaces[0]['release_candidates']:
            self.assertGreaterEqual(c['coverage'],.97)
            n=np.array(surfaces[0]['normal_world']);center=np.array(c['position_world_m'])
            from experiments.robot.libero.skill_pipeline.visual_observed_geometry import box_corners
            from scipy.spatial.transform import Rotation
            corners=box_corners(center,Rotation.from_euler('z',c['yaw_rad']).as_matrix(),np.array(target['collision_half_extents_m']))
            self.assertGreater((corners@n-surfaces[0]['offset_world_m']).min(),.004)

    def test_large_unobserved_gap_is_not_filled(self):
        x,y=np.meshgrid(np.arange(-.1,.101,.002),np.arange(-.07,.071,.002))
        points=np.c_[x.ravel(),y.ravel(),np.ones(x.size)]
        points=points[np.abs(points[:,0])>.035]
        result=support_candidates(points,dict(collision_half_extents_m=[.04,.02,.01]))
        # A rotated box can fit on either observed side, but never bridge the
        # missing central strip. Rejecting all side placements would be wrong.
        for surface in result:
            for c in surface['release_candidates']:
                extent=.04 if abs(c['yaw_rad'])<.1 else .02
                self.assertGreater(abs(c['position_world_m'][0])-extent,.032)
        from experiments.robot.libero.skill_pipeline.visual_observed_geometry import box_corners
        corners=box_corners(np.array([0.,0.,1.01]),np.eye(3),np.array([.04,.02,.01]))
        check=observed_place_check(corners,result[0],[.04,-.04],[np.array([0.,0.,1.01])]*10)
        self.assertFalse(check['ok'])
        self.assertLess(check['details']['observed_footprint_coverage'],.97)

    def test_closed_fingers_cannot_pass_release_check(self):
        plane=dict(normal_world=[0,0,1],offset_world_m=1,origin_world_m=[0,0,1],basis_world=np.eye(3).tolist(),uv_bounds_m=[[-1,-1],[1,1]])
        corners=np.array([[-.02,-.02,1],[.02,.02,1.02]])
        result=observed_place_check(corners,plane,[.01,-.01],[np.zeros(3)]*10)
        self.assertFalse(result['ok'])
        self.assertFalse(result['details']['gripper_open'])

if __name__=='__main__':unittest.main()
