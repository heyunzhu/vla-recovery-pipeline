"""A compound "open the drawer and put X inside" goal has to open the drawer first.

The task's *language* asks for the drawer to be opened, but its BDDL goal contains only the
placement (`inside(cheese, wooden_cabinet_1_top_region)`), so there is no `open` atom to build
the articulated subgoal from -- which is why the first attempt at this fix emitted nothing.
The part now comes from the articulation binding, and the drawer state comes from the same
joint lookup `place_in_open_drawer.evaluate_open_drawer_place` refuses a placement with.

Measured before the fix, on the baseline task04 problem: every `inside` goal failed with
`feasible=False, num_satisfying=0` while the problem recorded
`open_drawer_place: [{status: "closed", reason: "drawer is not open; this skill does not open it"}]`.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, Optional

from experiments.robot.libero.tiptop_repro.real_cutamp_adapter import (
    _articulation_part_for_region,
    _drawer_needs_opening,
)

REGION = "wooden_cabinet_1_top_region"
PART = "wooden_cabinet_1_top_region"
JOINT = "wooden_cabinet_1_top_level"
BODY = "wooden_cabinet_1_cabinet_top"


class _FakeScene:
    def __init__(self, structure: Optional[Dict[str, Any]] = None, joints: Optional[Dict[str, Any]] = None):
        self.articulation_structure = structure or {}
        self.joints = joints or {}


def _scene(reference_position: float, joint_range=(-0.16, 0.0)) -> _FakeScene:
    return _FakeScene(
        {
            JOINT: {
                "joint_name": JOINT,
                "body_name": BODY,
                "joint_range": list(joint_range),
                "reference_position": reference_position,
            }
        }
    )


def _config(enabled: bool = True, part_id: str = PART, top_level: bool = True) -> Dict[str, Any]:
    return {"articulation": {"enabled": enabled, "bindings": [{"part_id": part_id, "joint_name": JOINT}]}}


class DrawerNeedsOpeningTests(unittest.TestCase):
    def test_closed_travel_end_needs_opening(self):
        self.assertTrue(_drawer_needs_opening(_scene(0.0), REGION))

    def test_open_travel_end_does_not(self):
        self.assertFalse(_drawer_needs_opening(_scene(-0.16), REGION))

    def test_half_open_still_needs_opening(self):
        """OPEN_PROGRESS_MIN is 0.70, and evaluate_open_drawer_place refuses below it too."""
        self.assertTrue(_drawer_needs_opening(_scene(-0.08), REGION))

    def test_an_unknown_joint_is_not_claimed_to_need_opening(self):
        self.assertFalse(_drawer_needs_opening(_scene(0.0, joint_range=(0.0, 0.0)), REGION))
        self.assertFalse(_drawer_needs_opening(_FakeScene(), REGION))
        self.assertFalse(_drawer_needs_opening(_scene(0.0), ""))


class ArticulationPartForRegionTests(unittest.TestCase):
    def test_the_binding_naming_the_region_is_used(self):
        self.assertEqual(_articulation_part_for_region(_config(), REGION), PART)

    def test_without_a_config_there_is_no_part(self):
        self.assertIsNone(_articulation_part_for_region(None, REGION))
        self.assertIsNone(_articulation_part_for_region({}, REGION))
        self.assertIsNone(_articulation_part_for_region(_config(enabled=False), REGION))

    def test_a_binding_that_does_not_match_yields_nothing(self):
        self.assertIsNone(_articulation_part_for_region(_config(part_id="white_cabinet_1_top_region"), REGION))

    def test_the_level_token_fallback_matches_a_decorated_region(self):
        """e.g. a goal region `..._top_region_floor` against binding `..._top_region`."""
        self.assertEqual(
            _articulation_part_for_region(_config(), "wooden_cabinet_1_top_region_floor"),
            PART,
        )

    def test_options_are_also_read_from_the_hint_params(self):
        hints = {"params": _config()}
        self.assertEqual(_articulation_part_for_region(hints, REGION), PART)

    def test_an_empty_region_yields_nothing(self):
        self.assertIsNone(_articulation_part_for_region(_config(), ""))


if __name__ == "__main__":
    unittest.main()
