"""Small pure-XML/math tests; physical integration validation is separate."""
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
import numpy as np

spec=importlib.util.spec_from_file_location('boundary',Path(__file__).with_name('targeted_boundary_entrypoint.py'))
boundary=importlib.util.module_from_spec(spec);spec.loader.exec_module(boundary)


class BoundaryTests(unittest.TestCase):
    def test_identity_box_stretch_preserves_mass_density(self):
        xml='<mujoco><asset/><worldbody><body name="box"><geom type="box" size="1 2 3" density="100"/><site pos="0 0 3"/></body></worldbody></mujoco>'
        root=ET.fromstring(boundary.stretch_xml(xml,'box',.75))
        geom=root.find('.//geom')
        np.testing.assert_allclose(np.fromstring(geom.get('size'),sep=' '),[1,2,2.25])
        self.assertAlmostEqual(float(geom.get('density')),.0+100/.75)
        self.assertEqual(root.find('.//site').get('pos'),'0.0 0.0 2.25')

    def test_quarter_turn_scales_correct_collision_axis(self):
        xml='<mujoco><asset/><worldbody><body name="box"><geom type="box" size="1 2 3" quat="1 0 1 0"/></body></worldbody></mujoco>'
        root=ET.fromstring(boundary.stretch_xml(xml,'box',.75))
        np.testing.assert_allclose(np.fromstring(root.find('.//geom').get('size'),sep=' '),[.75,2,3])

    def test_arbitrary_rotation_rejected(self):
        xml='<mujoco><asset/><worldbody><body name="box"><geom type="box" size="1 2 3" quat="0.9238795 0.3826834 0 0"/></body></worldbody></mujoco>'
        with self.assertRaises(ValueError):boundary.stretch_xml(xml,'box',.75)

    def test_mesh_reference_cloned_not_shared_scaled(self):
        xml='<mujoco><asset><mesh name="m" file="x.msh" scale="1 2 3"/></asset><worldbody><body name="box"><geom type="mesh" mesh="m"/></body><body name="other"><geom type="mesh" mesh="m"/></body></worldbody></mujoco>'
        root=ET.fromstring(boundary.stretch_xml(xml,'box',.75))
        self.assertEqual(root.find('.//body[@name="other"]/geom').get('mesh'),'m')
        self.assertEqual(root.find('.//mesh[@name="m"]').get('scale'),'1 2 3')
        self.assertEqual(len(root.findall('.//mesh')),2)

    def test_invalid_range_and_missing_body_rejected(self):
        for factor in (.1,2):
            with self.assertRaises(ValueError):boundary.stretch_xml('<mujoco/>','x',factor)
        with self.assertRaises(ValueError):boundary.stretch_xml('<mujoco/>','x',.75)


if __name__=='__main__':unittest.main()
