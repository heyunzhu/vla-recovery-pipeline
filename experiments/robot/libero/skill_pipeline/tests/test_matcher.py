from __future__ import annotations

import unittest

from experiments.robot.libero.skill_pipeline.matcher import (
    diagnose_skills,
    eval_applies_to,
    eval_predicate,
    eval_trigger,
    match_recovery_hints,
    match_skills,
)
from experiments.robot.libero.skill_pipeline.schema import spec_from_mapping


def _skill(priority: int, **trigger):
    return spec_from_mapping(
        {
            "id": f"s{priority}",
            "kind": "repair",
            "hook": "before_trajectory_step",
            "priority": priority,
            "backend": "keep_gripper_closed",
            "trigger": {"all": [{key: value} for key, value in trigger.items()]},
        }
    )


class MatcherTests(unittest.TestCase):
    def test_object_followed_none_is_not_true(self):
        self.assertFalse(eval_predicate("object_followed_lift", True, {"object_followed": None}))
        self.assertTrue(eval_predicate("object_followed_lift", True, {"object_followed": True}))

    def test_label_and_aperture(self):
        state = {"label": "Pick(alphabet_soup)", "aperture": 0.03, "object_followed": True}
        self.assertTrue(
            eval_trigger(
                {
                    "all": [
                        {"object_followed_lift": True},
                        {"label_matches": r"pick\(|movefree"},
                        {"aperture_gt": 0.02},
                    ]
                },
                state,
            )
        )

    def test_gripper_cmd_gt(self):
        self.assertTrue(eval_predicate("gripper_cmd_gt", 0.5, {"gripper_cmd": 0.8}))
        self.assertFalse(eval_predicate("gripper_cmd_gt", 0.5, {"gripper_cmd": -1.0}))
        self.assertFalse(eval_predicate("gripper_cmd_gt", 0.5, {"gripper_cmd": None}))

    def test_priority_one_match(self):
        low = _skill(1, object_followed_lift=True)
        high = _skill(50, object_followed_lift=True)
        hit = match_skills([low, high], "before_trajectory_step", {"object_followed": True})
        self.assertIsNotNone(hit)
        self.assertEqual(hit.skill.id, "s50")

    def test_match_skills_respects_repair_applies_to(self):
        bowl = spec_from_mapping(
            {
                "id": "bowl_stall",
                "kind": "repair",
                "hook": "after_pi0_query",
                "priority": 50,
                "backend": "cutamp_recover",
                "applies_to": {"all": [{"target_name_matches": "bowl"}]},
                "trigger": {"all": [{"aperture_lt": 0.02}]},
            }
        )
        book = spec_from_mapping(
            {
                "id": "book_approach",
                "kind": "repair",
                "hook": "after_pi0_query",
                "priority": 40,
                "backend": "cutamp_recover",
                "applies_to": {"all": [{"target_name_matches": "book"}]},
                "trigger": {"all": [{"aperture_lt": 0.02}]},
            }
        )
        book_state = {"target_name": "black_book_1_main", "aperture": 0.01}
        bowl_state = {"target_name": "akita_black_bowl_1_main", "aperture": 0.01}

        self.assertEqual(match_skills([bowl, book], "after_pi0_query", book_state).skill.id, "book_approach")
        self.assertEqual(match_skills([bowl, book], "after_pi0_query", bowl_state).skill.id, "bowl_stall")
        self.assertIsNone(match_skills([bowl], "after_pi0_query", book_state))

    def test_ee_stalled(self):
        history = [[0.0, 0.0, 0.0], [0.001, 0.0, 0.0], [0.002, 0.0, 0.0], [0.002, 0.0, 0.001]]
        self.assertTrue(eval_predicate("ee_stalled", True, {"ee_history": history}))
        moving = history + [[0.2, 0.0, 0.0]]
        self.assertFalse(eval_predicate("ee_stalled", {"window": 4, "max_disp_m": 0.015}, {"ee_history": moving[-4:]}))

    def test_wrong_pick_target_predicates_require_known_nearest_object(self):
        state = {
            "aperture": 0.005,
            "target_ee_distance_m": 0.22,
            "nearest_pickable_distance_m": 0.04,
            "nearest_pickable_is_target": False,
            "vla_pick_target_status": "non_target_near",
        }
        self.assertTrue(eval_predicate("target_ee_distance_gt", 0.12, state))
        self.assertTrue(eval_predicate("nearest_pickable_distance_lt", 0.09, state))
        self.assertTrue(eval_predicate("nearest_pickable_is_target", False, state))
        self.assertTrue(eval_predicate("vla_pick_target_status_is", "non_target_near", state))
        self.assertFalse(eval_predicate("nearest_pickable_is_target", False, {"nearest_pickable_is_target": None}))

    def test_wrong_pick_target_trigger(self):
        self.assertTrue(
            eval_trigger(
                {
                    "all": [
                        {"aperture_lt": 0.02},
                        {"nearest_pickable_is_target": False},
                        {"nearest_pickable_distance_lt": 0.09},
                        {"target_ee_distance_gt": 0.12},
                    ]
                },
                {
                    "aperture": 0.004,
                    "nearest_pickable_is_target": False,
                    "nearest_pickable_distance_m": 0.05,
                    "target_ee_distance_m": 0.21,
                },
            )
        )
        self.assertFalse(
            eval_trigger(
                {
                    "all": [
                        {"aperture_lt": 0.02},
                        {"nearest_pickable_is_target": False},
                        {"nearest_pickable_distance_lt": 0.09},
                        {"target_ee_distance_gt": 0.12},
                    ]
                },
                {
                    "aperture": 0.004,
                    "nearest_pickable_is_target": True,
                    "nearest_pickable_distance_m": 0.03,
                    "target_ee_distance_m": 0.04,
                },
            )
        )

    def test_wrong_object_intent_trigger_uses_status_not_aperture(self):
        trigger = {
            "any": [
                {"vla_pick_target_status_is": "non_target_intent"},
                {"vla_pick_target_status_is": "non_target_intent_with_motion"},
            ]
        }
        self.assertTrue(eval_trigger(trigger, {"vla_pick_target_status": "non_target_intent", "aperture": 0.04}))
        self.assertTrue(
            eval_trigger(trigger, {"vla_pick_target_status": "non_target_intent_with_motion", "aperture": 0.04})
        )
        self.assertFalse(eval_trigger(trigger, {"vla_pick_target_status": "non_target_near", "aperture": 0.001}))

    def test_wrong_object_intent_metric_predicates(self):
        state = {
            "intent_object_is_target": False,
            "intent_min_xy_distance_m": 0.04,
            "wrong_object_intent_margin_m": 0.12,
            "wrong_object_intent_persist_queries": 3,
            "target_future_min_xy_distance_m": 0.18,
        }
        self.assertTrue(eval_predicate("intent_object_is_target", False, state))
        self.assertTrue(eval_predicate("intent_min_xy_distance_lt", 0.075, state))
        self.assertTrue(eval_predicate("wrong_object_intent_margin_gt", 0.055, state))
        self.assertTrue(eval_predicate("wrong_object_intent_persist_queries_gte", 3, state))
        self.assertTrue(eval_predicate("target_future_min_xy_distance_gt", 0.085, state))
        self.assertFalse(eval_predicate("intent_object_is_target", False, {"intent_object_is_target": None}))

    def test_wrong_object_progress_predicates(self):
        state = {
            "wrong_progress_object_total_motion_m": 0.31,
            "wrong_progress_object_goal_xy_distance_m": 0.08,
            "wrong_progress_object_is_intent": True,
            "wrong_progress_object_is_held": False,
            "wrong_progress_target_static": True,
            "vla_wrong_object_progress_status": "wrong_object_at_goal",
        }
        self.assertTrue(eval_predicate("wrong_progress_object_total_motion_gt", 0.06, state))
        self.assertTrue(eval_predicate("wrong_progress_object_goal_xy_distance_lt", 0.18, state))
        self.assertTrue(eval_predicate("wrong_progress_object_is_intent", True, state))
        self.assertTrue(eval_predicate("wrong_progress_object_is_held", False, state))
        self.assertTrue(eval_predicate("wrong_progress_target_static", True, state))
        self.assertTrue(eval_predicate("vla_wrong_object_progress_status_is", "wrong_object_at_goal", state))
        self.assertFalse(eval_predicate("wrong_progress_target_static", True, {"wrong_progress_target_static": None}))

    def test_flat_box_open_hand_stall_trigger(self):
        state = {
            "aperture": 0.039,
            "holding_status": "handempty_or_unconfirmed",
            "wrong_progress_target_static": True,
            "target_ee_distance_m": 0.056,
            "nearest_pickable_is_target": True,
            "intent_object_is_target": True,
            "ee_history": [
                [0.050, -0.197, 0.448],
                [0.050, -0.198, 0.447],
                [0.050, -0.199, 0.446],
                [0.050, -0.199, 0.446],
            ],
        }
        self.assertTrue(
            eval_trigger(
                {
                    "all": [
                        {"aperture_gt": 0.025},
                        {"holding_status_is": "handempty_or_unconfirmed"},
                        {"wrong_progress_target_static": True},
                        {"target_ee_distance_lt": 0.09},
                        {"nearest_pickable_is_target": True},
                        {"ee_stalled": {"window": 4, "max_disp_m": 0.015}},
                    ],
                    "any": [{"intent_object_is_target": True}],
                },
                state,
            )
        )

    def test_flat_box_wrong_object_intent_stall_trigger(self):
        state = {
            "aperture": 0.040,
            "holding_status": "handempty_or_unconfirmed",
            "wrong_progress_target_static": True,
            "intent_object_is_target": False,
            "wrong_object_intent_persist_queries": 4,
            "wrong_object_intent_margin_m": 0.13,
            "intent_min_xy_distance_m": 0.04,
            "nearest_pickable_is_target": False,
            "nearest_pickable_distance_m": 0.06,
            "target_ee_distance_m": 0.19,
            "target_future_min_xy_distance_m": 0.18,
            "ee_history": [
                [-0.064, -0.154, 0.447],
                [-0.059, -0.155, 0.446],
                [-0.058, -0.155, 0.446],
                [-0.058, -0.155, 0.446],
            ],
        }
        self.assertTrue(
            eval_trigger(
                {
                    "all": [
                        {"aperture_gt": 0.025},
                        {"holding_status_is": "handempty_or_unconfirmed"},
                        {"wrong_progress_target_static": True},
                        {"intent_object_is_target": False},
                        {"wrong_object_intent_persist_queries_gte": 3},
                        {"wrong_object_intent_margin_gt": 0.055},
                        {"intent_min_xy_distance_lt": 0.075},
                        {"nearest_pickable_is_target": False},
                        {"nearest_pickable_distance_lt": 0.24},
                        {"target_ee_distance_gt": 0.10},
                        {"target_future_min_xy_distance_gt": 0.085},
                        {"ee_stalled": {"window": 4, "max_disp_m": 0.015}},
                    ]
                },
                state,
            )
        )

    def test_diagnose_skills_reports_failed_predicates(self):
        skill = spec_from_mapping(
            {
                "id": "book_pick",
                "kind": "repair",
                "hook": "after_pi0_query",
                "priority": 5,
                "backend": "cutamp_recover",
                "applies_to": {"all": [{"target_name_matches": "book"}]},
                "trigger": {
                    "all": [
                        {"aperture_gt": 0.025},
                        {"target_ee_distance_lt": 0.30},
                    ],
                    "any": [{"nearest_pickable_is_target": True}],
                },
            }
        )
        diag = diagnose_skills(
            [skill],
            "after_pi0_query",
            {
                "target_name": "black_book_1_main",
                "aperture": 0.04,
                "target_ee_distance_m": 0.42,
                "nearest_pickable_is_target": False,
            },
        )
        self.assertEqual(len(diag), 1)
        self.assertTrue(diag[0]["applies_to"]["passed"])
        self.assertFalse(diag[0]["trigger"]["passed"])
        self.assertIn("target_ee_distance_lt", diag[0]["trigger"]["failed_all"])
        self.assertEqual(diag[0]["trigger"]["failed_any"], ["nearest_pickable_is_target"])

    def test_articulated_blocker_trigger_uses_status(self):
        trigger = {
            "all": [
                {"aperture_gt": 0.03},
                {"holding_status_is": "handempty_or_unconfirmed"},
                {"target_ee_distance_gt": 0.10},
                {"vla_articulated_blocker_status_is": "blocked_open_drawer_before_pick"},
            ]
        }
        self.assertTrue(
            eval_trigger(
                trigger,
                {
                    "aperture": 0.04,
                    "holding_status": "handempty_or_unconfirmed",
                    "target_ee_distance_m": 0.18,
                    "vla_articulated_blocker_status": "blocked_open_drawer_before_pick",
                },
            )
        )
        self.assertFalse(
            eval_trigger(
                trigger,
                {
                    "aperture": 0.04,
                    "holding_status": "handempty_or_unconfirmed",
                    "target_ee_distance_m": 0.18,
                    "vla_articulated_blocker_status": "task_allows_drawer_interaction",
                },
            )
        )

    def test_recovery_hints_do_not_compete_for_primary_hook(self):
        repair = _skill(10, aperture_gt=0.02)
        hint = spec_from_mapping(
            {
                "id": "bowl_hint",
                "kind": "recovery_hint",
                "priority": 99,
                "applies_to": {"all": [{"target_name_matches": "bowl"}]},
                "recovery_hints": {"grasp_profile": "default"},
            }
        )
        hit = match_skills([hint, repair], "before_trajectory_step", {"aperture": 0.03, "target_name": "bowl"})
        self.assertIsNotNone(hit)
        self.assertEqual(hit.skill.id, "s10")

    def test_recovery_hint_applies_to(self):
        self.assertTrue(
            eval_applies_to(
                {
                    "all": [
                        {"target_name_matches": "bowl"},
                        {"task_language_matches": "on top of .*cabinet"},
                    ]
                },
                {
                    "target_name": "akita_black_bowl_2_main",
                    "task_description": "put the middle black bowl on top of the cabinet",
                },
            )
        )

    def test_recovery_hint_target_excludes(self):
        applies_to = {
            "all": [
                {"target_name_matches": "cream_cheese|alphabet_soup|box"},
                {"target_name_excludes": "alphabet_soup|can"},
            ]
        }
        self.assertTrue(eval_applies_to(applies_to, {"target_name": "cream_cheese_1_main"}))
        self.assertFalse(eval_applies_to(applies_to, {"target_name": "alphabet_soup_1_main"}))

    def test_recovery_hint_can_branch_on_target_orientation(self):
        applies_to = {
            "all": [
                {"target_name_matches": "milk|orange_juice"},
                {"target_orientation_is": "fallen"},
            ]
        }
        self.assertTrue(eval_applies_to(applies_to, {"target_name": "milk_1_main", "target_orientation": "fallen"}))
        self.assertFalse(eval_applies_to(applies_to, {"target_name": "milk_1_main", "target_orientation": "upright"}))
        self.assertFalse(eval_applies_to(applies_to, {"target_name": "milk_1_main"}))

    def test_bowl_stack_hint_can_match_goal_bowl(self):
        self.assertTrue(
            eval_applies_to(
                {
                    "all": [
                        {"task_language_matches": r"\bstack\b"},
                        {"target_name_matches": "bowl"},
                        {"goal_name_matches": "bowl"},
                    ]
                },
                {
                    "target_name": "akita_black_bowl_1_main",
                    "goal_name": "akita_black_bowl_2_main",
                    "task_description": "stack the black bowl at the front on the black bowl in the middle",
                },
            )
        )

    def test_recovery_hint_can_match_bddl_goal_surface_list(self):
        applies_to = {
            "all": [
                {"task_language_matches": r"\bto the right of the plate\b"},
                {"bddl_goal_surface_matches": r".*_table_plate_(left|right)_region$"},
            ]
        }
        self.assertTrue(
            eval_applies_to(
                applies_to,
                {
                    "task_description": "put the chocolate pudding to the right of the plate",
                    "bddl_goal_surfaces": ["living_room_table_plate_right_region"],
                },
            )
        )
        self.assertFalse(
            eval_applies_to(
                applies_to,
                {
                    "task_description": "put the mug on the right plate",
                    "bddl_goal_surfaces": ["plate_2_main"],
                },
            )
        )

    def test_match_recovery_hints_priority_ascending_for_merge(self):
        low = spec_from_mapping(
            {
                "id": "low_hint",
                "kind": "recovery_hint",
                "priority": 1,
                "applies_to": {"all": [{"target_name_matches": "bowl"}]},
                "recovery_hints": {"grasp_profile": "default"},
            }
        )
        high = spec_from_mapping(
            {
                "id": "high_hint",
                "kind": "recovery_hint",
                "priority": 50,
                "applies_to": {"all": [{"target_name_matches": "bowl"}]},
                "recovery_hints": {"grasp_profile": "bowl_rim_diagonal_mixed_topdown_v1"},
            }
        )
        hits = match_recovery_hints([high, low], {"target_name": "akita_black_bowl_1_main"})
        self.assertEqual([item.skill.id for item in hits], ["low_hint", "high_hint"])


if __name__ == "__main__":
    unittest.main()
