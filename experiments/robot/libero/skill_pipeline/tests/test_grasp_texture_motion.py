import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

scripts = Path(__file__).resolve().parents[5] / 'scripts/recovery/skill_pipeline'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('grasp_texture_probe', scripts/'probe_grasp_texture_motion.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class TextureCorrespondenceTests(unittest.TestCase):
    def test_translated_texture_and_brightness_offset(self):
        image = np.random.default_rng(11).normal(size=(90,90))
        patch = image[32:49,32:49]
        target = np.roll(image,(5,-7),axis=(0,1))*2+.3
        xy,score,margin = probe.match_patch(patch,target,(40,40))
        self.assertEqual(xy,(33,45))
        self.assertGreater(score,.999)
        self.assertGreater(margin,.015)
        back,score,_ = probe.match_patch(target[37:54,25:42],image,xy)
        self.assertEqual(back,(40,40))

    def test_repeated_texture_has_no_separated_peak_margin(self):
        yy,xx=np.indices((90,90));image=((xx%8)<4).astype(float)
        _,score,margin=probe.match_patch(image[32:49,32:49],image,(40,40))
        self.assertGreater(score,.99)
        self.assertLess(margin,.015)

    def test_flat_patch_is_not_a_confident_match(self):
        _,score,_=probe.match_patch(np.ones((17,17)),np.ones((90,90)),(40,40))
        self.assertLess(score,.90)
