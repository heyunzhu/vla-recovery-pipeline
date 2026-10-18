import unittest
import numpy as np
import os
from pathlib import Path
import sys
import tempfile
from scipy.spatial.transform import Rotation
from experiments.robot.libero.skill_pipeline.framewise_rgbd_tracker import register_cloud,transform
from experiments.robot.libero.skill_pipeline.resident_vision import JSONLineProcess


class FramewiseRegistrationTest(unittest.TestCase):
    def test_non_cylindrical_object_can_translate_and_tilt(self):
        rng=np.random.default_rng(4)
        cloud=rng.normal(size=(2400,3))
        cloud/=np.linalg.norm(cloud,axis=1)[:,None]
        cloud*=np.array([.024,.017,.08]);cloud[:,2]+=.95
        pose=np.eye(4);pose[:3,:3]=Rotation.from_euler('xy',[20,15],degrees=True).as_matrix()
        center=cloud.mean(0)
        pose[:3,3]=center-pose[:3,:3]@center+np.array([.03,.02,.01])
        observed=transform(cloud,pose)
        seed=np.eye(4);seed[:3,3]=observed.mean(0)-cloud.mean(0)
        fitted,report=register_cloud(cloud,observed,seed)
        self.assertTrue(report['accepted'])
        self.assertLess(Rotation.from_matrix(fitted[:3,:3]@pose[:3,:3].T).magnitude(),.015)
        self.assertLess(np.median(np.linalg.norm(transform(cloud,fitted)-observed,axis=1)),.001)

    def test_insufficient_observations_are_rejected(self):
        with self.assertRaises(ValueError):register_cloud(np.zeros((8,3)),np.zeros((8,3)),np.eye(4))

    def test_worker_reuses_one_process_and_shuts_down(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            worker=path/'worker.py'
            worker.write_text('import sys,json,os\nprint("startup log",flush=True)\nprint(\'RGBD_REPLY {"ready":true}\',flush=True)\nfor line in sys.stdin:\n r=json.loads(line)\n if r.get("shutdown"):break\n print("RGBD_REPLY "+json.dumps(dict(pid=os.getpid(),value=r["value"],cwd=os.getcwd())),flush=True)\n')
            process=JSONLineProcess([sys.executable,str(worker)],env=dict(os.environ),log_path=path/'worker.log',timeout=5,cwd=path)
            try:
                first=process.request(dict(value=1));second=process.request(dict(value=2))
                self.assertEqual(first['pid'],second['pid'])
                self.assertEqual(second['value'],2)
                self.assertEqual(Path(second['cwd']).resolve(),path.resolve())
            finally:process.close()
            self.assertIsNotNone(process.process.poll())


if __name__=='__main__':unittest.main()
