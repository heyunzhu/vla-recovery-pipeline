from __future__ import annotations

import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.geometry_profiles import load_geometry_profile_registry
from experiments.robot.libero.skill_pipeline.grounding_profiles import load_grounding_profile_registry
from experiments.robot.libero.skill_pipeline.matcher import eval_applies_to
from experiments.robot.libero.skill_pipeline.repair_profiles import load_repair_profile_registry
from experiments.robot.libero.skill_pipeline.schema import (
    SkillSchemaError,
    applies_to_schema_errors,
    infer_track,
    load_skill,
    resolve_mining_skills,
    resolve_online_skills,
    spec_from_mapping,
    trigger_schema_errors,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hold_then_pick_traj_opens.md"


class SchemaTests(unittest.TestCase):
    def test_fixture_parses(self):
        spec = load_skill(FIXTURE)
        self.assertEqual(spec.id, "hold_then_pick_traj_opens")
        self.assertEqual(spec.hook, "before_trajectory_step")
        self.assertEqual(spec.backend, "keep_gripper_closed")

    def test_rejects_unknown_predicate(self):
        with self.assertRaises(SkillSchemaError):
            spec_from_mapping(
                {
                    "id": "bad",
                    "kind": "repair",
                    "hook": "before_trajectory_step",
                    "backend": "keep_gripper_closed",
                    "trigger": {"all": [{"contacts_gt": 3}]},
                }
            )

    def test_rejects_query_index_and_xyz(self):
        errors = trigger_schema_errors({"all": [{"label_matches": "query_idx: 12"}]})
        self.assertTrue(any("query" in item for item in errors))
        errors = trigger_schema_errors({"all": [{"aperture_gt": "[0.12, 0.03, 0.81]"}]})
        self.assertTrue(any("xyz" in item for item in errors))

    def test_repo_index_loads_online_bowl_skill(self):
        root = Path(__file__).resolve().parents[5] / "skill_packs/libero90_legacy/skills/_index.yaml"
        specs = resolve_online_skills(root)
        grounding_registry = load_grounding_profile_registry(index_path=root)
        geometry_registry = load_geometry_profile_registry(index_path=root)
        repair_registry = load_repair_profile_registry(index_path=root)

        def expanded_recovery_hints(skill_id: str) -> dict:
            spec = next(item for item in specs if item.id == skill_id)
            hints = grounding_registry.expand_recovery_hints(spec.recovery_hints)
            hints = geometry_registry.expand_recovery_hints(hints)
            return repair_registry.expand_recovery_hints(hints)

        self.assertEqual(
            [spec.id for spec in specs],
            [
                "vla_wrong_object_progress_recovery",
                "flat_box_wrong_object_intent_stall_recovery",
                "book_caddy_pick_approach_recovery",
                "vla_wrong_object_intent_conservative",
                "book_pick_approach_recovery",
                "vla_closed_near_non_target_pick",
                "flat_box_pick_open_hand_stall_recovery",
                "bowl_pick_blocked_by_open_drawer",
                "mug_pick_approach_or_stall_recovery",
                "bowl_pick_preclose_near_target",
                "bowl_pick_empty_close_stall",
                "grasp_carton_fallen_body_side",
                "grasp_carton_upright_body_side",
                "grasp_tomato_sauce_can_body_orthogonal_lower",
                "grasp_bowl_rim_away_from_open_drawer_topdown",
                "grasp_flat_box_topdown_short_side_deep",
                "grasp_moka_pot_handle_topdown",
                "grasp_book_upright_topdown",
                "grasp_can_body_lower_side",
                "grasp_flat_box_topdown_short_side",
                "grasp_task38_white_bowl_microwave_high_lift",
                "grasp_small_shallow_bowl_rim_diagonal_topdown",
                "grasp_bowl_rim_diagonal_mixed_topdown",
                "grasp_mug_body_side_avoid_handle",
                "place_task38_held_transfer_keep_z",
                "desk_caddy_compartment_grounding",
                "desk_caddy_side_region_grounding",
                "place_caddy_held_object_xy_align",
                "plate_side_region_grounding",
                "task35_mug_front_region_grounding",
                "task38_plate_right_region_grounding",
                "desk_caddy_compartment_geometry",
                "desk_caddy_side_region_geometry",
                "plate_side_region_geometry",
                "task35_mug_front_region_geometry",
                "task38_plate_right_region_geometry",
                "top_drawer_container_grounding",
                "cabinet_top_support_grounding",
                "shelf_support_grounding",
                "top_drawer_inner_floor_geometry",
                "bowl_stack_support_grounding",
                "container_inside_region",
                "shelf_region_inner_floor_geometry",
                "bowl_stack_support_geometry",
            ],
        )
        self.assertTrue(all(spec.track == "pair" for spec in specs))
        self.assertTrue(all(spec.online for spec in specs))
        self.assertTrue(all(spec.applies_to for spec in specs if spec.kind in {"repair", "trigger"}))
        self.assertNotIn("vla_wrong_object_pick_intent", [spec.id for spec in specs])
        self.assertEqual(specs[0].kind, "repair")
        self.assertEqual(specs[1].kind, "repair")
        self.assertEqual(specs[2].kind, "repair")
        self.assertEqual(specs[0].id, "vla_wrong_object_progress_recovery")
        self.assertEqual(specs[1].id, "flat_box_wrong_object_intent_stall_recovery")
        self.assertEqual(specs[2].id, "book_caddy_pick_approach_recovery")
        self.assertEqual(specs[3].id, "vla_wrong_object_intent_conservative")
        self.assertEqual(specs[4].id, "book_pick_approach_recovery")
        book_repair = next(spec for spec in specs if spec.id == "book_caddy_pick_approach_recovery")
        self.assertTrue(
            eval_applies_to(
                book_repair.applies_to,
                {
                    "target_name": "black_book_1_main",
                    "goal_name": "desk_caddy_1_main",
                    "task_description": "pick up the book and place it in the front compartment of the caddy",
                    "bddl_goal_surfaces": ["desk_caddy_1_front_contain_region"],
                },
            )
        )
        self.assertFalse(
            eval_applies_to(
                book_repair.applies_to,
                {
                    "target_name": "akita_black_bowl_1_main",
                    "goal_name": "plate_1_main",
                    "task_description": "put the black bowl on the plate",
                    "bddl_goal_surfaces": ["plate_1_main"],
                },
            )
        )
        self.assertEqual(specs[5].id, "vla_closed_near_non_target_pick")
        wrong_close = next(spec for spec in specs if spec.id == "vla_closed_near_non_target_pick")
        self.assertFalse(eval_applies_to(wrong_close.applies_to, {"target_name": "black_book_1_main"}))
        flat_wrong_stall = next(spec for spec in specs if spec.id == "flat_box_wrong_object_intent_stall_recovery")
        self.assertTrue(eval_applies_to(flat_wrong_stall.applies_to, {"target_name": "chocolate_pudding_1_main"}))
        self.assertFalse(eval_applies_to(flat_wrong_stall.applies_to, {"target_name": "cream_cheese_1_main"}))
        flat_target_stall = next(spec for spec in specs if spec.id == "flat_box_pick_open_hand_stall_recovery")
        self.assertTrue(eval_applies_to(flat_target_stall.applies_to, {"target_name": "chocolate_pudding_1_main"}))
        self.assertTrue(eval_applies_to(flat_target_stall.applies_to, {"target_name": "cream_cheese_1_main"}))
        self.assertFalse(eval_applies_to(flat_target_stall.applies_to, {"target_name": "akita_black_bowl_1_main"}))
        wrong_intent = next(spec for spec in specs if spec.id == "vla_wrong_object_intent_conservative")
        self.assertTrue(eval_applies_to(wrong_intent.applies_to, {"target_name": "black_book_1_main"}))
        self.assertTrue(eval_applies_to(wrong_intent.applies_to, {"target_name": "porcelain_mug_1_main"}))
        book_generic = next(spec for spec in specs if spec.id == "book_pick_approach_recovery")
        self.assertTrue(eval_applies_to(book_generic.applies_to, {"target_name": "yellow_book_1_main"}))
        mug_repair = next(spec for spec in specs if spec.id == "mug_pick_approach_or_stall_recovery")
        self.assertTrue(eval_applies_to(mug_repair.applies_to, {"target_name": "red_coffee_mug_1_main"}))
        blocker = next(spec for spec in specs if spec.id == "bowl_pick_blocked_by_open_drawer")
        self.assertEqual(blocker.recovery_hints["params"]["repair_profile"], "entry_lift_escape_current_away_blocker_v1")
        self.assertTrue(eval_applies_to(blocker.applies_to, {"target_name": "akita_black_bowl_1_main"}))
        self.assertFalse(eval_applies_to(blocker.applies_to, {"target_name": "black_book_1_main"}))
        blocker_hints = expanded_recovery_hints("bowl_pick_blocked_by_open_drawer")
        self.assertEqual(
            blocker_hints["params"]["executor"]["recovery_entry_escape_profile"],
            "current_away_blocker",
        )
        self.assertEqual(blocker_hints["params"]["executor"]["recovery_entry_retreat_m"], 0.080)
        self.assertEqual(blocker.trigger["all"][3]["vla_articulated_blocker_status_is"], "blocked_open_drawer_before_pick")
        preclose = next(spec for spec in specs if spec.id == "bowl_pick_preclose_near_target")
        self.assertEqual(preclose.recovery_hints["params"]["repair_profile"], "entry_lift_open_hand_small_v1")
        preclose_hints = expanded_recovery_hints("bowl_pick_preclose_near_target")
        self.assertEqual(preclose_hints["params"]["executor"]["recovery_entry_lift_m"], 0.045)
        fallback = next(spec for spec in specs if spec.id == "bowl_pick_empty_close_stall")
        self.assertEqual(fallback.recovery_hints["params"]["repair_profile"], "entry_lift_open_hand_small_v1")
        fallback_hints = expanded_recovery_hints("bowl_pick_empty_close_stall")
        self.assertEqual(fallback_hints["params"]["executor"]["recovery_entry_lift_m"], 0.045)
        grasp = next(spec for spec in specs if spec.id == "grasp_bowl_rim_diagonal_mixed_topdown")
        self.assertEqual(grasp.kind, "recovery_hint")
        self.assertEqual(grasp.recovery_hints["grasp_profile"], "bowl_rim_diagonal_mixed_topdown_v1")
        self.assertTrue(eval_applies_to(grasp.applies_to, {"target_name": "akita_black_bowl_2_main"}))
        self.assertFalse(eval_applies_to(grasp.applies_to, {"target_name": "white_bowl_1_main"}))
        task38_place = next(spec for spec in specs if spec.id == "place_task38_held_transfer_keep_z")
        self.assertEqual(task38_place.recovery_hints["params"]["place_profile"], "task38_held_transfer_keep_z_v1")
        self.assertTrue(
            eval_applies_to(
                task38_place.applies_to,
                {
                    "target_name": "white_bowl_1_main",
                    "task_description": "put the white bowl to the right of the plate",
                },
            )
        )
        self.assertFalse(
            eval_applies_to(
                task38_place.applies_to,
                {
                    "target_name": "akita_black_bowl_1_main",
                    "task_description": "put the black bowl to the right of the plate",
                },
            )
        )
        open_drawer_grasp = next(spec for spec in specs if spec.id == "grasp_bowl_rim_away_from_open_drawer_topdown")
        self.assertEqual(
            open_drawer_grasp.recovery_hints["grasp_profile"],
            "bowl_rim_away_from_open_drawer_topdown_v1",
        )
        self.assertTrue(
            eval_applies_to(
                open_drawer_grasp.applies_to,
                {
                    "target_name": "akita_black_bowl_1_main",
                    "task_description": "put the black bowl on top of the cabinet",
                },
            )
        )
        self.assertFalse(
            eval_applies_to(
                open_drawer_grasp.applies_to,
                {
                    "target_name": "akita_black_bowl_1_main",
                    "task_description": "put the black bowl on the plate",
                },
            )
        )
        shallow_grasp = next(spec for spec in specs if spec.id == "grasp_small_shallow_bowl_rim_diagonal_topdown")
        self.assertEqual(shallow_grasp.recovery_hints["grasp_profile"], "bowl_rim_small_shallow_diagonal_topdown_v1")
        task38_lift_grasp = next(spec for spec in specs if spec.id == "grasp_task38_white_bowl_microwave_high_lift")
        self.assertEqual(task38_lift_grasp.recovery_hints["grasp_profile"], "bowl_rim_small_shallow_diagonal_topdown_v1")
        task38_lift_executor = task38_lift_grasp.recovery_hints["params"]["executor"]
        self.assertEqual(task38_lift_executor["grasp_lift_probe_m"], 0.085)
        self.assertEqual(task38_lift_executor["grasp_lift_probe_max_steps"], 30)
        self.assertEqual(task38_lift_executor["grasp_lift_follow_m"], 0.030)
        self.assertTrue(
            eval_applies_to(
                task38_lift_grasp.applies_to,
                {
                    "target_name": "white_bowl_1_main",
                    "task_description": "put the white bowl to the right of the plate",
                },
            )
        )
        self.assertFalse(
            eval_applies_to(
                task38_lift_grasp.applies_to,
                {
                    "target_name": "white_bowl_1_main",
                    "task_description": "put the white bowl on the plate",
                },
            )
        )
        self.assertTrue(
            eval_applies_to(
                shallow_grasp.applies_to,
                {
                    "target_name": "white_bowl_1_main",
                    "task_description": "put the white bowl to the right of the plate",
                },
            )
        )
        self.assertTrue(
            eval_applies_to(
                shallow_grasp.applies_to,
                {
                    "target_name": "white_bowl_1_main",
                    "task_description": "put the white bowl on the plate",
                },
            )
        )
        mug_grasp = next(spec for spec in specs if spec.id == "grasp_mug_body_side_avoid_handle")
        self.assertEqual(mug_grasp.recovery_hints["grasp_profile"], "mug_body_side_avoid_handle_v1")
        book_grasp = next(spec for spec in specs if spec.id == "grasp_book_upright_topdown")
        self.assertEqual(book_grasp.recovery_hints["grasp_profile"], "flat_box_topdown_short_side_book_v1")
        self.assertEqual(book_grasp.recovery_hints["params"]["executor"]["grasp_close_max_above_m"], 0.20)
        self.assertTrue(eval_applies_to(book_grasp.applies_to, {"target_name": "black_book_1_main"}))
        self.assertFalse(eval_applies_to(book_grasp.applies_to, {"target_name": "cream_cheese_1_main"}))
        flat_box_grasp = next(spec for spec in specs if spec.id == "grasp_flat_box_topdown_short_side")
        self.assertEqual(flat_box_grasp.recovery_hints["grasp_profile"], "flat_box_topdown_short_side_v1")
        deep_flat_box_grasp = next(spec for spec in specs if spec.id == "grasp_flat_box_topdown_short_side_deep")
        self.assertEqual(deep_flat_box_grasp.recovery_hints["grasp_profile"], "flat_box_topdown_short_side_deep_v1")
        flat_box_predicates = flat_box_grasp.applies_to["all"]
        flat_box_matches = [item["target_name_matches"] for item in flat_box_predicates if "target_name_matches" in item]
        flat_box_excludes = [item["target_name_excludes"] for item in flat_box_predicates if "target_name_excludes" in item]
        self.assertFalse(any("alphabet_soup" in str(item) for item in flat_box_matches))
        self.assertTrue(any("alphabet_soup" in str(item) for item in flat_box_excludes))
        chocolate_pudding_state = {"target_name": "chocolate_pudding_1_main"}
        self.assertFalse(eval_applies_to(flat_box_grasp.applies_to, chocolate_pudding_state))
        self.assertTrue(eval_applies_to(deep_flat_box_grasp.applies_to, chocolate_pudding_state))
        can_grasp = next(spec for spec in specs if spec.id == "grasp_can_body_lower_side")
        self.assertEqual(can_grasp.recovery_hints["grasp_profile"], "can_body_lower_side_v1")
        tomato_can_grasp = next(spec for spec in specs if spec.id == "grasp_tomato_sauce_can_body_orthogonal_lower")
        self.assertEqual(tomato_can_grasp.recovery_hints["grasp_profile"], "can_body_orthogonal_lower_side_v1")
        moka_grasp = next(spec for spec in specs if spec.id == "grasp_moka_pot_handle_topdown")
        self.assertEqual(moka_grasp.recovery_hints["grasp_profile"], "moka_pot_handle_topdown_v1")
        self.assertTrue(eval_applies_to(moka_grasp.applies_to, {"target_name": "moka_pot_1_main"}))
        self.assertFalse(eval_applies_to(moka_grasp.applies_to, {"target_name": "chefmate_8_frypan_1_main"}))
        fallen_carton = next(spec for spec in specs if spec.id == "grasp_carton_fallen_body_side")
        self.assertEqual(fallen_carton.recovery_hints["grasp_profile"], "carton_fallen_body_side_v1")
        self.assertIn({"target_orientation_is": "fallen"}, fallen_carton.applies_to["all"])
        upright_carton = next(spec for spec in specs if spec.id == "grasp_carton_upright_body_side")
        self.assertEqual(upright_carton.recovery_hints["grasp_profile"], "carton_upright_body_side_v1")
        self.assertIn({"target_orientation_is": "upright"}, upright_carton.applies_to["all"])
        mug_region = next(spec for spec in specs if spec.id == "task35_mug_front_region_geometry")
        self.assertEqual(
            mug_region.recovery_hints["params"]["geometry_profile"],
            "task35_mug_front_region_geometry_v1",
        )
        mug_region_hints = expanded_recovery_hints("task35_mug_front_region_geometry")
        self.assertEqual(
            mug_region_hints["params"]["geometry_hints"]["placement_region"]["region_name"],
            "kitchen_table_porcelain_mug_front_region",
        )
        plate_right = next(spec for spec in specs if spec.id == "task38_plate_right_region_geometry")
        self.assertEqual(
            plate_right.recovery_hints["params"]["geometry_profile"],
            "task38_plate_right_region_geometry_v1",
        )
        plate_right_hints = expanded_recovery_hints("task38_plate_right_region_geometry")
        self.assertEqual(
            plate_right_hints["params"]["geometry_hints"]["placement_region"]["region_name"],
            "kitchen_table_plate_right_region",
        )
        plate_side_grounding = next(spec for spec in specs if spec.id == "plate_side_region_grounding")
        self.assertTrue(
            eval_applies_to(
                plate_side_grounding.applies_to,
                {
                    "target_name": "chocolate_pudding_1_main",
                    "task_description": "put the chocolate pudding to the left of the plate",
                    "bddl_goal_surfaces": ["living_room_table_plate_left_region"],
                },
            )
        )
        self.assertFalse(
            eval_applies_to(
                plate_side_grounding.applies_to,
                {
                    "target_name": "akita_black_bowl_1_main",
                    "task_description": "put the black bowl on the right plate",
                    "bddl_goal_surfaces": ["plate_2_main"],
                },
            )
        )
        plate_side_geometry = next(spec for spec in specs if spec.id == "plate_side_region_geometry")
        self.assertEqual(
            plate_side_geometry.recovery_hints["params"]["geometry_profile"],
            "plate_side_region_geometry_v1",
        )
        plate_side_hint = expanded_recovery_hints("plate_side_region_geometry")["params"]["geometry_hints"][
            "placement_region"
        ]
        self.assertEqual(plate_side_hint["intent"], "bddl_table_rect")
        self.assertTrue(plate_side_hint["bounds_from_bddl_region"])
        caddy_side_grounding = next(spec for spec in specs if spec.id == "desk_caddy_side_region_grounding")
        self.assertTrue(
            eval_applies_to(
                caddy_side_grounding.applies_to,
                {
                    "target_name": "red_coffee_mug_1_main",
                    "goal_name": "desk_caddy_1_main",
                    "task_description": "pick up the red mug and place it to the right compartment of the caddy",
                    "bddl_goal_surfaces": ["study_table_desk_caddy_right_region"],
                },
            )
        )
        self.assertFalse(
            eval_applies_to(
                caddy_side_grounding.applies_to,
                {
                    "target_name": "black_book_1_main",
                    "goal_name": "desk_caddy_1_main",
                    "task_description": "pick up the book and place it in the right compartment of the caddy",
                    "bddl_goal_surfaces": ["desk_caddy_1_right_contain_region"],
                },
            )
        )
        caddy_side_geometry = next(spec for spec in specs if spec.id == "desk_caddy_side_region_geometry")
        self.assertEqual(
            caddy_side_geometry.recovery_hints["params"]["geometry_profile"],
            "desk_caddy_side_region_geometry_v1",
        )
        caddy_side_hint = expanded_recovery_hints("desk_caddy_side_region_geometry")["params"]["geometry_hints"][
            "placement_region"
        ]
        self.assertEqual(caddy_side_hint["intent"], "bddl_table_rect")
        self.assertTrue(caddy_side_hint["bounds_from_bddl_region"])
        self.assertTrue(caddy_side_hint["region_name_from_bddl_goal"])
        caddy_grounding = next(spec for spec in specs if spec.id == "desk_caddy_compartment_grounding")
        self.assertEqual(
            caddy_grounding.recovery_hints["params"]["grounding_profile"],
            "desk_caddy_compartment_v1",
        )
        caddy_surface_hint = expanded_recovery_hints("desk_caddy_compartment_grounding")["params"][
            "grounding_hints"
        ]["placement_surface"]
        self.assertEqual(caddy_surface_hint["intent"], "container_compartment")
        self.assertIn("*_left_contain_region", caddy_surface_hint["region_name_matches"])
        self.assertNotIn("compartment", caddy_surface_hint)
        caddy_geometry = next(spec for spec in specs if spec.id == "desk_caddy_compartment_geometry")
        self.assertEqual(
            caddy_geometry.recovery_hints["params"]["geometry_profile"],
            "desk_caddy_compartment_inner_floor_v1",
        )
        caddy_geometry_hints = expanded_recovery_hints("desk_caddy_compartment_geometry")
        caddy_region_hint = caddy_geometry_hints["params"]["geometry_hints"]["placement_region"]
        self.assertEqual(caddy_region_hint["intent"], "compartment_inner_floor")
        self.assertIn("*_front_contain_region", caddy_region_hint["region_name_matches"])
        self.assertIn("*_left_contain_region", caddy_region_hint["region_name_matches"])
        self.assertNotIn("compartment", caddy_region_hint)
        self.assertTrue(caddy_region_hint["exclude_source_collision"])
        self.assertTrue(caddy_region_hint["exclude_table_collision"])
        self.assertEqual(caddy_region_hint["place_yaw_policy"], "thin_horizontal_along_world_x")
        self.assertEqual(
            caddy_geometry_hints["params"]["executor"]["place_yaw_after_hover"],
            "world_z_thin_x",
        )
        self.assertNotIn("grasp_profile", caddy_geometry.recovery_hints)
        self.assertEqual(caddy_region_hint["release_mode"], "high_drop_into_compartment")
        self.assertEqual(caddy_region_hint["place_candidate_policy"], "center_and_entry_high_drop")
        shelf_grounding = next(spec for spec in specs if spec.id == "shelf_support_grounding")
        self.assertEqual(shelf_grounding.recovery_hints["params"]["grounding_profile"], "shelf_support_v1")
        shelf_grounding_hints = expanded_recovery_hints("shelf_support_grounding")
        self.assertEqual(
            shelf_grounding_hints["params"]["grounding_hints"]["placement_surface"]["intent"],
            "shelf_support",
        )
        shelf_geometry = next(spec for spec in specs if spec.id == "shelf_region_inner_floor_geometry")
        self.assertEqual(
            shelf_geometry.recovery_hints["params"]["geometry_profile"],
            "shelf_region_inner_floor_geometry_v1",
        )
        shelf_geometry_hints = expanded_recovery_hints("shelf_region_inner_floor_geometry")
        self.assertEqual(
            shelf_geometry_hints["params"]["geometry_hints"]["placement_region"]["intent"],
            "shelf_region_inner_floor",
        )
        caddy_place = next(spec for spec in specs if spec.id == "place_caddy_held_object_xy_align")
        self.assertEqual(caddy_place.recovery_hints["params"]["place_profile"], "caddy_book_compartment_align_budget_v1")
        self.assertNotIn("grasp_profile", caddy_place.recovery_hints)
        cabinet = next(spec for spec in specs if spec.id == "cabinet_top_support_grounding")
        self.assertEqual(cabinet.recovery_hints["params"]["grounding_profile"], "cabinet_top_support_v1")
        surface_hint = expanded_recovery_hints("cabinet_top_support_grounding")["params"]["grounding_hints"][
            "placement_surface"
        ]
        self.assertEqual(surface_hint["intent"], "top_support")
        self.assertIn("*_cabinet_top", surface_hint["prefer"])
        stack = next(spec for spec in specs if spec.id == "bowl_stack_support_grounding")
        self.assertEqual(stack.recovery_hints["params"]["grounding_profile"], "bowl_stack_support_v1")
        stack_hint = expanded_recovery_hints("bowl_stack_support_grounding")["params"]["grounding_hints"][
            "support_object"
        ]
        self.assertEqual(stack_hint["intent"], "stack_support")
        self.assertEqual(stack_hint["object_class"], "bowl")
        stack_geometry = next(spec for spec in specs if spec.id == "bowl_stack_support_geometry")
        self.assertEqual(
            stack_geometry.recovery_hints["params"]["geometry_profile"],
            "bowl_stack_support_geometry_v1",
        )
        geometry_hint = expanded_recovery_hints("bowl_stack_support_geometry")["params"]["geometry_hints"][
            "movable_support_surface"
        ]
        self.assertEqual(geometry_hint["intent"], "stack_support")
        container_region = next(spec for spec in specs if spec.id == "container_inside_region")
        self.assertEqual(
            container_region.recovery_hints["params"]["geometry_profile"],
            "container_inside_region_geometry_v1",
        )
        container_hint = expanded_recovery_hints("container_inside_region")["params"]["geometry_hints"][
            "placement_region"
        ]
        self.assertEqual(container_hint["intent"], "container_inner_floor")
        self.assertEqual(container_hint["relation"], "inside")

    def test_diagnostics_skip_hook(self):
        spec = spec_from_mapping({"id": "note", "kind": "diagnostics", "name": "offline"})
        self.assertEqual(spec.kind, "diagnostics")
        self.assertFalse(spec.online)

    def test_track_defaults_and_path_inference(self):
        spec = spec_from_mapping(
            {
                "id": "ok",
                "kind": "repair",
                "hook": "after_pi0_query",
                "backend": "cutamp_recover",
                "trigger": {"all": [{"ee_stalled": True}]},
            }
        )
        self.assertEqual(spec.track, "pair")
        self.assertEqual(infer_track({}, "skills/fail_only/repair/x.md"), "fail_only")
        fail_spec = spec_from_mapping(
            {
                "id": "stall",
                "kind": "repair",
                "track": "fail_only",
                "hook": "after_pi0_query",
                "backend": "cutamp_recover",
                "trigger": {"all": [{"ee_stalled": True}]},
            }
        )
        self.assertEqual(fail_spec.track, "fail_only")
        self.assertFalse(fail_spec.online)

    def test_recovery_hints_are_parsed_conservatively(self):
        spec = spec_from_mapping(
            {
                "id": "bowl_recover",
                "kind": "repair",
                "hook": "after_pi0_query",
                "backend": "cutamp_recover",
                "trigger": {"all": [{"aperture_gt": 0.02}]},
                "recovery_hints": {
                    "grasp_profile": "hollow_bowl_rim_topdown",
                    "target": "target",
                    "params": {"rim_depth_m": 0.024},
                },
            }
        )
        self.assertEqual(spec.recovery_hints["grasp_profile"], "hollow_bowl_rim_topdown")
        self.assertEqual(spec.recovery_hints["target"], "target")
        self.assertEqual(spec.recovery_hints["params"]["rim_depth_m"], 0.024)

    def test_recovery_hints_keep_profile_names_for_capability_gate(self):
        spec = spec_from_mapping(
            {
                "id": "custom_profile",
                "kind": "repair",
                "hook": "after_pi0_query",
                "backend": "cutamp_recover",
                "trigger": {"all": [{"aperture_gt": 0.02}]},
                "recovery_hints": {"grasp_profile": "write_python_code"},
            }
        )
        self.assertEqual(spec.recovery_hints["grasp_profile"], "write_python_code")

    def test_recovery_hint_schema(self):
        spec = spec_from_mapping(
            {
                "id": "bowl_hint",
                "kind": "recovery_hint",
                "track": "pair",
                "scope": "grasp",
                "priority": 10,
                "applies_to": {"all": [{"target_name_matches": "bowl"}]},
                "recovery_hints": {"grasp_profile": "bowl_rim_diagonal_mixed_topdown_v1"},
            }
        )
        self.assertEqual(spec.kind, "recovery_hint")
        self.assertEqual(spec.scope, "grasp")
        self.assertEqual(spec.applies_to["all"][0]["target_name_matches"], "bowl")
        self.assertTrue(spec.online)

    def test_recovery_hint_rejects_trigger(self):
        with self.assertRaises(SkillSchemaError):
            spec_from_mapping(
                {
                    "id": "bad_hint",
                    "kind": "recovery_hint",
                    "trigger": {"all": [{"aperture_gt": 0.02}]},
                    "recovery_hints": {"grasp_profile": "default"},
                }
            )

    def test_applies_to_rejects_unknown_predicate(self):
        errors = applies_to_schema_errors({"all": [{"aperture_gt": 0.02}]})
        self.assertTrue(any("unknown applies_to predicate" in item for item in errors))

    def test_repair_applies_to_rejects_unknown_predicate(self):
        with self.assertRaises(SkillSchemaError):
            spec_from_mapping(
                {
                    "id": "bad_repair_scope",
                    "kind": "repair",
                    "hook": "after_pi0_query",
                    "backend": "cutamp_recover",
                    "applies_to": {"all": [{"aperture_gt": 0.02}]},
                    "trigger": {"all": [{"ee_stalled": True}]},
                }
            )

    def test_fail_only_cannot_be_online_index(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "fail_only" / "repair"
            skill.mkdir(parents=True)
            (skill / "stall.md").write_text(
                "\n".join(
                    [
                        "---",
                        "id: stall",
                        "kind: repair",
                        "track: fail_only",
                        "hook: after_pi0_query",
                        "backend: cutamp_recover",
                        "trigger:",
                        "  all:",
                        "    - ee_stalled: true",
                        "---",
                        "",
                        "draft",
                    ]
                ),
                encoding="utf-8",
            )
            index = root / "_index.yaml"
            index.write_text("online:\n  - fail_only/repair/stall.md\n", encoding="utf-8")
            with self.assertRaises(SkillSchemaError):
                resolve_online_skills(index)

    def test_mining_index_loads_fail_only_without_online(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "fail_only" / "trigger"
            skill.mkdir(parents=True)
            (skill / "stall.md").write_text(
                "\n".join(
                    [
                        "---",
                        "id: stall",
                        "kind: trigger",
                        "track: fail_only",
                        "hook: after_pi0_query",
                        "backend: cutamp_recover",
                        "trigger:",
                        "  all:",
                        "    - ee_stalled: true",
                        "---",
                        "",
                        "draft",
                    ]
                ),
                encoding="utf-8",
            )
            index = root / "_index.yaml"
            index.write_text("online: []\nfail_only:\n  - fail_only/trigger/stall.md\n", encoding="utf-8")
            mined = resolve_mining_skills(index)
            self.assertEqual([item.id for item in mined], ["stall"])
            self.assertEqual(resolve_online_skills(index), [])


if __name__ == "__main__":
    unittest.main()
