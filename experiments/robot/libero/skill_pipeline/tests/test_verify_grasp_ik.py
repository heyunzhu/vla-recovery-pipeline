"""The per-candidate table `verify_grasp_ik.py` prints, checked without cuRobo.

The probe itself needs cuRobo and a task04 problem, but the part that decides what each
candidate *is* -- which object axis the fingers close across, how deep the grasp sits -- is
pure geometry over the pack profile. Pinning it here means the printed table can be trusted
before it is used to explain an IK count.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from experiments.robot.libero.tiptop_repro.grasp_profiles import registry_from_adapter_paths
from scripts.recovery.skill_pipeline.verify_grasp_ik import grasp_candidate_table

PACK = "libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914"
PROFILE = "cream_cheese_flat_box_topdown_deep_v1"

CANONICAL = dict(
    dims=[0.04267, 0.08122, 0.01787],
    pose=[0.6013, 0.1344, -0.0031, 0.7071, -0.0, 0.0, -0.7071],
    vertical_axis=2,
    long_axis=1,
    across_axis=0,
)
UNCANONICAL = dict(
    dims=[0.01787, 0.04267, 0.08122],
    pose=[0.6013, 0.1344, -0.0031, 0.0, 0.7071, -0.0, -0.7071],
    vertical_axis=0,
    long_axis=2,
    across_axis=1,
)


def _rows(frame: dict):
    adapter = Path(__file__).resolve().parents[5] / "skill_packs" / PACK / "code" / "grasp_profiles.py"
    registry = registry_from_adapter_paths([adapter])
    return grasp_candidate_table(PROFILE, frame["dims"], frame["pose"], registry=registry)


class GraspCandidateTableTests(unittest.TestCase):
    def test_table_has_24_candidates_in_four_yaw_groups_of_six(self):
        for name, frame in (("canonical", CANONICAL), ("uncanonical", UNCANONICAL)):
            with self.subTest(frame=name):
                rows = _rows(frame)
                self.assertEqual(len(rows), 24)
                self.assertEqual([row["rank"] for row in rows], list(range(24)))
                yaws = {}
                for row in rows:
                    yaws[round(row["world_yaw_deg"], 1)] = yaws.get(round(row["world_yaw_deg"], 1), 0) + 1
                self.assertEqual(len(yaws), 4)
                self.assertEqual(set(yaws.values()), {6})

    def test_two_depths_and_three_long_axis_offsets(self):
        for frame in (CANONICAL, UNCANONICAL):
            rows = _rows(frame)
            depths = {round(row["depth_from_top_m"], 6) for row in rows}
            self.assertEqual(len(depths), 2)
            for depth in depths:
                self.assertEqual(sum(1 for row in rows if round(row["depth_from_top_m"], 6) == depth), 12)
            offsets = {round(float(row["local_xyz"][frame["long_axis"]]), 6) for row in rows}
            self.assertEqual(len(offsets), 3)
            self.assertIn(0.0, offsets)

    def test_axes_follow_the_object_frame(self):
        for name, frame in (("canonical", CANONICAL), ("uncanonical", UNCANONICAL)):
            with self.subTest(frame=name):
                rows = _rows(frame)
                for row in rows:
                    self.assertEqual(row["vertical_axis"], frame["vertical_axis"])
                    self.assertEqual(row["long_axis"], frame["long_axis"])
                    self.assertEqual(row["across_axis"], frame["across_axis"])
                    # a tool-down grasp closes across a horizontal axis
                    for column in ("x", "y"):
                        self.assertNotEqual(row["closing_axis_local"][column], frame["vertical_axis"])
                    self.assertEqual(
                        {row["closing_axis_local"]["x"], row["closing_axis_local"]["y"]},
                        {frame["long_axis"], frame["across_axis"]},
                    )

    def test_half_the_candidates_need_the_long_extent_and_half_the_short_one(self):
        """Under 'grasp x closes': 12 need 42.67 mm, 12 need 81.22 mm -- the split is not noise."""
        for name, frame in (("canonical", CANONICAL), ("uncanonical", UNCANONICAL)):
            with self.subTest(frame=name):
                rows = _rows(frame)
                spans = {}
                for row in rows:
                    span = round(row["straddle_if_x_closes_m"] * 1000, 2)
                    spans[span] = spans.get(span, 0) + 1
                self.assertEqual(spans, {42.67: 12, 81.22: 12})
                # and the y convention is the mirror image of it
                mirrored = {}
                for row in rows:
                    span = round(row["straddle_if_y_closes_m"] * 1000, 2)
                    mirrored[span] = mirrored.get(span, 0) + 1
                self.assertEqual(mirrored, {42.67: 12, 81.22: 12})

    def test_limit_truncates_without_reordering(self):
        rows = _rows(CANONICAL)
        limited = grasp_candidate_table(
            PROFILE,
            CANONICAL["dims"],
            CANONICAL["pose"],
            registry=registry_from_adapter_paths(
                [Path(__file__).resolve().parents[5] / "skill_packs" / PACK / "code" / "grasp_profiles.py"]
            ),
            limit=5,
        )
        self.assertEqual(len(limited), 5)
        self.assertEqual([row["xyzrpy"] for row in limited], [row["xyzrpy"] for row in rows[:5]])


if __name__ == "__main__":
    unittest.main()
