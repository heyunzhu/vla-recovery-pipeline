import unittest
import numpy as np
from scipy.spatial.transform import Rotation
from experiments.robot.libero.skill_pipeline.visual_observed_geometry import (
    fit_observed_cuboid, fit_observed_support, cuboid_geometry)
from experiments.robot.libero.skill_pipeline.visual_task_binding import (
    VisualTaskBinding, require_geometry_binding)
from experiments.robot.libero.skill_pipeline.tests.test_visual_task_binding import _scene, _object


class ObservedGeometryTest(unittest.TestCase):
    @staticmethod
    def box_surface():
        rng = np.random.default_rng(21)
        dims = np.array([.08,.045,.02])
        faces = []
        for axis in range(3):
            p = rng.uniform(-.5,.5,(700,3))*dims
            p[:,axis] = dims[axis]/2
            faces.append(p)
        rotation = Rotation.from_euler('xyz',[17,23,38],degrees=True).as_matrix()
        center = np.array([-.08,.1,.95])
        points = np.concatenate(faces)@rotation.T+center
        points += rng.normal(0,.0001,points.shape)
        return points,dims,rotation,center

    def test_tilted_box_from_three_visible_faces(self):
        points,dims,rotation,center = self.box_surface()
        model = fit_observed_cuboid(points)
        self.assertTrue(model['planning_allowed'],model['reasons'])
        np.testing.assert_allclose(sorted(model['dimensions_m']),sorted(dims),atol=.002)
        np.testing.assert_allclose(model['center_world_m'],center,atol=.001)
        geoms = cuboid_geometry(model)['geoms']
        self.assertEqual(geoms[0]['shape'],'box')
        self.assertEqual(model['simulator_geometry_used'],False)
        normals = np.array([p['normal'] for p in model['plane_evidence']])
        self.assertTrue(np.all(np.max(np.abs(normals@rotation),axis=0)>.985))

    def test_one_face_cannot_claim_known_thickness(self):
        x,y=np.meshgrid(np.linspace(-.04,.04,25),np.linspace(-.02,.02,20))
        points=np.c_[x.ravel(),y.ravel(),np.ones(x.size)]
        model=fit_observed_cuboid(points)
        self.assertFalse(model['planning_allowed'])
        with self.assertRaises(ValueError):cuboid_geometry(model)

    def test_dense_top_view_does_not_erase_sparse_side_faces(self):
        points,_,_,_=self.box_surface()
        sparse=np.concatenate([points[:700],points[700:1400:4],points[1400::14]])
        dense=np.concatenate([sparse,np.repeat(points[:700],6,axis=0)])
        self.assertTrue(fit_observed_cuboid(sparse)['planning_allowed'])
        self.assertTrue(fit_observed_cuboid(dense)['planning_allowed'])

    def test_inclined_shelf_is_not_flattened(self):
        x,y=np.meshgrid(np.linspace(-.1,.1,35),np.linspace(-.05,.05,25))
        points=np.c_[x.ravel(),y.ravel(),1+np.tan(np.pi/6)*y.ravel()]
        model=fit_observed_support(points)
        self.assertFalse(model['planning_allowed'])
        self.assertEqual(model['candidates'],[])
        self.assertAlmostEqual(model['inclined_surfaces'][0]['tilt_degrees'],30,places=4)

    def test_horizontal_plane_does_not_certify_holes_or_footprint(self):
        x,y=np.meshgrid(np.linspace(-.1,.1,35),np.linspace(-.05,.05,25))
        points=np.c_[x.ravel(),y.ravel(),np.ones(x.size)]
        model=fit_observed_support(points)
        self.assertTrue(model['candidates'])
        self.assertFalse(model['planning_allowed'])

    def test_refused_binding_has_explicit_reason(self):
        scene=_scene(_object('obj_001','bowl',0,0))
        binding=VisualTaskBinding(scene.snapshot_id,reason='target_not_observed')
        with self.assertRaisesRegex(ValueError,'target_not_observed'):
            require_geometry_binding(scene,binding)

    def test_stale_id_is_rejected_before_lookup(self):
        scene=_scene(_object('obj_001','bowl',0,0))
        binding=VisualTaskBinding(scene.snapshot_id,status='bound_ids',target_id='obj_missing',goal_id='obj_001')
        with self.assertRaisesRegex(ValueError,'invalid'):
            require_geometry_binding(scene,binding)


if __name__=='__main__':unittest.main()
