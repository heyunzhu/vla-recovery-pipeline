from __future__ import annotations

import unittest

from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language


class VisualLanguagePromptsTest(unittest.TestCase):
    def test_spatial_task_uses_only_task_words(self) -> None:
        self.assertEqual(
            prompts_from_task_language(
                "pick up the black bowl between the plate and the ramekin and place it on the plate"
            ),
            {"bowl": "black bowl", "plate": "plate", "ramekin": "ramekin"},
        )

    def test_simple_pick_place(self) -> None:
        self.assertEqual(
            prompts_from_task_language("Take the mug and put it into the caddy."),
            {"mug": "mug", "caddy": "caddy"},
        )

    def test_refuses_unsupported_goals_and_conflicting_descriptions(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported visual goal"):
            prompts_from_task_language("pick up the bowl and place it to the left of the plate")
        with self.assertRaisesRegex(ValueError, "unsupported task language"):
            prompts_from_task_language("open the drawer")
        with self.assertRaisesRegex(ValueError, "conflicting descriptions"):
            prompts_from_task_language("pick up the black bowl and place it on the red bowl")
        with self.assertRaisesRegex(ValueError, "unsupported object phrase"):
            prompts_from_task_language(
                "pick up the black bowl not between the plate and the ramekin and place it on the plate"
            )


if __name__ == "__main__":
    unittest.main()
