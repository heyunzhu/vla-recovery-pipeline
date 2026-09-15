from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.packer import pack_fail_set, pack_pair
from experiments.robot.libero.skill_pipeline.trace_schema import EpisodeWriter, TraceSchemaError, make_query_record


def _query(**kwargs):
    base = {
        "task_id_1based": 56,
        "episode_idx": 0,
        "seed": 1,
        "query_idx": 0,
        "env_step": 10,
        "mode": "vla",
        "ee_xyz": [0.1, 0.0, 0.8],
        "ee_quat": [0, 0, 0, 1],
        "gripper_qpos": [0.04, -0.04],
        "gripper_aperture": 0.04,
        "gripper_cmd": -1.0,
        "target_name": "alphabet_soup",
        "target_xyz": [0.2, 0.0, 0.9],
        "holding_status": "handempty_or_unconfirmed",
        "holding_object": None,
        "bilateral": None,
        "object_followed": None,
        "logvar_gripper_first": -3.0,
        "residual_score": None,
        "hook_fired": False,
        "skill_id": "",
    }
    base.update(kwargs)
    return make_query_record(base)


class TraceAndPackerTests(unittest.TestCase):
    def test_object_followed_rejects_zero(self):
        with self.assertRaises(TraceSchemaError):
            make_query_record({**_query(), "object_followed": 0})

    def test_nearest_pickable_is_target_rejects_zero(self):
        with self.assertRaises(TraceSchemaError):
            make_query_record({**_query(), "nearest_pickable_is_target": 0})

    def test_intent_object_is_target_rejects_zero(self):
        with self.assertRaises(TraceSchemaError):
            make_query_record({**_query(), "intent_object_is_target": 0})

    def test_pack_pair_does_not_inline_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            success = root / "success"
            fail = root / "fail"
            for path, ok, aperture0, aperture1 in (
                (success, True, 0.04, 0.005),
                (fail, False, 0.04, 0.03),
            ):
                writer = EpisodeWriter(path)
                writer.append_query(_query(query_idx=0, gripper_aperture=aperture0))
                writer.append_query(_query(query_idx=1, gripper_aperture=aperture1, gripper_cmd=1.0))
                writer.append_recovery({"kind": "lift_probe", "object_followed": True, "label": "Pick(x)"})
                writer.write_episode_json({"success": ok, "episode_idx": 0, "seed": 1, "task_description": "t56"})
            out = root / "pair.json"
            payload = pack_pair(success, [fail], out, task="t56")
            text = out.read_text(encoding="utf-8")
            self.assertNotIn("inline", json.dumps(payload.get("failures")[0].get("queries")))
            self.assertTrue(payload["recovery_trace_paths"])
            self.assertIn("recovery_trace.jsonl", text)
            self.assertNotIn('"object_followed": true,\n      "label"', text)
            self.assertEqual(payload["track"], "pair")
            self.assertFalse(payload["recovery_required"])

    def test_pack_fail_set_allows_empty_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fail = root / "fail"
            writer = EpisodeWriter(fail)
            writer.append_query(_query(query_idx=0, gripper_aperture=0.04))
            writer.append_query(_query(query_idx=1, gripper_aperture=0.04, ee_xyz=[0.11, 0.0, 0.8]))
            writer.write_episode_json(
                {"success": False, "episode_idx": 0, "seed": 90, "task_description": "close the top drawer"}
            )
            out = root / "fail_set.json"
            payload = pack_fail_set([fail], out, task="task01")
            self.assertEqual(payload["track"], "fail_only")
            self.assertIsNone(payload["success"])
            self.assertFalse(payload["failures"][0]["recovery_available"])
            self.assertEqual(payload["failures"][0]["recovery_event_count"], 0)
            self.assertTrue(any(frame["slot"] == "stall" for frame in payload["aligned_frames"]))


if __name__ == "__main__":
    unittest.main()
