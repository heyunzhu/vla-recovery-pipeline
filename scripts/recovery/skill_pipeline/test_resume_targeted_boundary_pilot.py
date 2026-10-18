import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import resume_targeted_boundary_pilot as resume


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.p1=patch.object(resume.base,'O',self.root);self.p1.start()
        self.p2=patch.object(resume,'S',self.root/'resume_v1');self.p2.start()
        (self.root/'targeted_boundary_entrypoint.py').write_text('test overlay')
        self.job={'id':'A_test','panel':'grasp','task':1,'config':{}}

    def tearDown(self):
        self.p2.stop();self.p1.stop();self.tmp.cleanup()

    def sample(self,idx,success=False,error=None,seed=None):
        d=self.root/'jobs'/'A_test'
        p=d/'run'/'task01'/f'ep{idx:02d}';p.mkdir(parents=True,exist_ok=True)
        h=hashlib.sha256((self.root/'targeted_boundary_entrypoint.py').read_bytes()).hexdigest()
        (d/'command.json').write_text(json.dumps({'entrypoint_sha256':h}))
        (p/'episode.json').write_text(json.dumps({'success':success,'seed':idx+1 if seed is None else seed,'init_state_idx':idx}))
        (p/'recovery_trace.jsonl').write_text(json.dumps({'error':error})+'\n')
        return p

    def test_failure_is_completed_robot_outcome(self):
        self.sample(0,False);self.sample(2,True)
        self.assertEqual(set(resume.completed(self.job)),{0,2})

    def test_identity_mismatch_rejected(self):
        self.sample(0,seed=99)
        with self.assertRaises(ValueError):resume.completed(self.job)

    def test_infrastructure_not_robot_failure(self):
        self.sample(0,error='runner_failed:127: missing python')
        with self.assertRaises(RuntimeError):resume.completed(self.job)

    def test_partial_json_not_completed(self):
        p=self.sample(0);(p/'episode.json').write_text('{')
        self.assertEqual(resume.completed(self.job),{})

    def test_lane_preserves_missing_seed_and_init_indices(self):
        (self.root/'manifest.json').write_text(json.dumps({'jobs':[self.job]}))
        self.sample(0);self.sample(2)
        calls=[]
        def fake_run(j,d,n):
            argv=resume.base.command(j,d,n)
            start=int(argv[argv.index('--episode_index_start')+1]);calls.append((start,n))
            self.assertEqual(argv[argv.index('--episode_seed_start')+1],'1')
            for idx in range(start,start+n):self.sample(idx)
        original=resume.base.command
        try:
            with patch.object(resume.base,'run',fake_run):resume.lane(0,'test')
        finally:resume.base.command=original
        self.assertEqual(calls,[(1,1),(3,2)])


if __name__=='__main__':unittest.main()
