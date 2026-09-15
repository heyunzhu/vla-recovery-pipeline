from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from experiments.robot.libero.skill_pipeline.dispatcher import dispatch, merge_recovery_hints
from experiments.robot.libero.skill_pipeline.geometry_profiles import load_geometry_profile_registry
from experiments.robot.libero.skill_pipeline.grounding_profiles import load_grounding_profile_registry
from experiments.robot.libero.skill_pipeline.hooks import HookBus
from experiments.robot.libero.skill_pipeline.place_profiles import load_place_profile_registry
from experiments.robot.libero.skill_pipeline.repair_profiles import load_repair_profile_registry
from experiments.robot.libero.skill_pipeline.runtime import SkillRuntime
from experiments.robot.libero.skill_pipeline.schema import SkillSchemaError, load_skill, spec_from_mapping
from experiments.robot.libero.tiptop_repro.grasp_profiles import (
    GRASP_PROFILE_ADAPTER_PARAM_KEY,
    load_grasp_profile_registry,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hold_then_pick_traj_opens.md"
REPO_ROOT = Path(__file__).resolve().parents[5]


class DispatcherTests(unittest.TestCase):
    def test_keep_closed_overrides_hold(self):
        spec = load_skill(FIXTURE)
        runtime = SkillRuntime([spec])
        runtime.after_gripper_close({"object_followed": True, "aperture": 0.03, "gripper_close_value": 1.0})
        decision = runtime.before_trajectory_step(
            {
                "label": "Pick(alphabet_soup)",
                "aperture": 0.03,
                "gripper_close_value": 1.0,
            }
        )
        self.assertIsNotNone(decision)
        self.assertTrue(decision["keep_gripper_closed"])
        self.assertEqual(decision["gripper_hold_value"], 1.0)
        self.assertEqual(decision["skill_id"], spec.id)

    def test_unknown_backend(self):
        spec = load_skill(FIXTURE)
        spec.backend = "not_a_backend"
        bus = HookBus([spec])
        match = bus.emit(
            "before_trajectory_step",
            {"object_followed": True, "label": "Pick(x)", "aperture": 0.04},
        )
        self.assertIsNotNone(match)
        with self.assertRaises(SkillSchemaError):
            dispatch(match, {})

    def test_cutamp_recover_carries_recovery_hints(self):
        spec = spec_from_mapping(
            {
                "id": "bowl_rim_recover",
                "kind": "repair",
                "hook": "after_pi0_query",
                "backend": "cutamp_recover",
                "trigger": {"all": [{"aperture_gt": 0.02}]},
                "recovery_hints": {"grasp_profile": "hollow_bowl_rim_topdown", "target": "target"},
            }
        )
        bus = HookBus([spec])
        match = bus.emit("after_pi0_query", {"aperture": 0.03})
        self.assertIsNotNone(match)
        decision = dispatch(match, {"aperture": 0.03})
        self.assertTrue(decision.enter_recovery)
        self.assertEqual(decision.recovery_hints["grasp_profile"], "hollow_bowl_rim_topdown")
        self.assertEqual(decision.to_dict()["recovery_hints"]["target"], "target")

    def test_runtime_merges_matching_recovery_hint_policies(self):
        repair = spec_from_mapping(
            {
                "id": "bowl_pick_empty_close_stall",
                "kind": "repair",
                "hook": "after_pi0_query",
                "priority": 60,
                "backend": "cutamp_recover",
                "trigger": {
                    "all": [
                        {"aperture_lt": 0.02},
                        {"holding_status_is": "handempty_or_unconfirmed"},
                    ]
                },
            }
        )
        grasp = spec_from_mapping(
            {
                "id": "grasp_bowl_rim_diagonal_mixed_topdown",
                "kind": "recovery_hint",
                "priority": 50,
                "applies_to": {"all": [{"target_name_matches": "bowl"}]},
                "recovery_hints": {
                    "grasp_profile": "bowl_rim_diagonal_mixed_topdown_v1",
                    "target": "target",
                },
            }
        )
        grounding = spec_from_mapping(
            {
                "id": "cabinet_top_support_grounding",
                "kind": "recovery_hint",
                "priority": 45,
                "applies_to": {"all": [{"task_language_matches": "on top of .*cabinet"}]},
                "recovery_hints": {
                    "params": {
                        "grounding_hints": {
                            "placement_surface": {
                                "prefer": ["*_cabinet_top", "*_top"],
                                "avoid": ["*_handle"],
                            }
                        }
                    }
                },
            }
        )
        runtime = SkillRuntime([repair, grasp, grounding])
        decision = runtime.after_pi0_query(
            {
                "aperture": 0.01,
                "holding_status": "handempty_or_unconfirmed",
                "target_name": "akita_black_bowl_2_main",
                "task_description": "put the middle black bowl on top of the cabinet",
            }
        )
        self.assertIsNotNone(decision)
        hints = decision["recovery_hints"]
        self.assertEqual(hints["grasp_profile"], "bowl_rim_diagonal_mixed_topdown_v1")
        self.assertEqual(hints["target"], "target")
        self.assertIn("*_cabinet_top", hints["params"]["grounding_hints"]["placement_surface"]["prefer"])
        self.assertEqual(
            [item["skill_id"] for item in hints["params"]["hint_sources"]],
            [
                "cabinet_top_support_grounding",
                "grasp_bowl_rim_diagonal_mixed_topdown",
            ],
        )

    def test_merge_recovery_hints_records_scalar_conflict(self):
        merged = merge_recovery_hints(
            [
                ("low", 1, {"grasp_profile": "default", "params": {"prefer": ["a"]}}),
                ("high", 50, {"grasp_profile": "native", "params": {"prefer": ["b", "a"]}}),
            ]
        )
        self.assertEqual(merged["grasp_profile"], "native")
        self.assertEqual(merged["params"]["prefer"], ["b", "a"])
        self.assertEqual(merged["params"]["hint_conflicts"][0]["path"], "grasp_profile")

    def test_runtime_merges_bowl_stack_support_hint(self):
        repair = spec_from_mapping(
            {
                "id": "bowl_pick_empty_close_stall",
                "kind": "repair",
                "hook": "after_pi0_query",
                "priority": 60,
                "backend": "cutamp_recover",
                "trigger": {"all": [{"aperture_lt": 0.02}]},
            }
        )
        stack = spec_from_mapping(
            {
                "id": "bowl_stack_support_grounding",
                "kind": "recovery_hint",
                "priority": 44,
                "applies_to": {
                    "all": [
                        {"task_language_matches": r"\bstack\b"},
                        {"target_name_matches": "bowl"},
                        {"goal_name_matches": "bowl"},
                    ]
                },
                "recovery_hints": {
                    "params": {
                        "geometry_hints": {
                            "movable_support_surface": {
                                "intent": "stack_support",
                                "object_class": "bowl",
                                "require_movable": True,
                            }
                        }
                    }
                },
            }
        )
        runtime = SkillRuntime([repair, stack])
        decision = runtime.after_pi0_query(
            {
                "aperture": 0.01,
                "target_name": "akita_black_bowl_1_main",
                "goal_name": "akita_black_bowl_2_main",
                "task_description": "stack the black bowl at the front on the black bowl in the middle",
            }
        )
        self.assertIsNotNone(decision)
        support = decision["recovery_hints"]["params"]["geometry_hints"]["movable_support_surface"]
        self.assertEqual(support["intent"], "stack_support")
        self.assertEqual(
            [item["skill_id"] for item in decision["recovery_hints"]["params"]["hint_sources"]],
            ["bowl_stack_support_grounding"],
        )

    def test_forced_recovery_query_applies_matching_recovery_hints(self):
        grasp = spec_from_mapping(
            {
                "id": "grasp_flat_box_topdown_short_side_deep",
                "kind": "recovery_hint",
                "priority": 55,
                "applies_to": {"all": [{"target_name_matches": "cream_cheese|butter"}]},
                "recovery_hints": {"grasp_profile": "flat_box_topdown_short_side_deep_v1"},
            }
        )
        runtime = SkillRuntime([grasp])
        decision = runtime.force_recovery_query({"target_name": "cream_cheese_1_main"})
        self.assertTrue(decision["enter_recovery"])
        self.assertEqual(decision["recovery_hints"]["grasp_profile"], "flat_box_topdown_short_side_deep_v1")
        self.assertIn("grasp_flat_box_topdown_short_side_deep", decision["skill_id"])

    def test_runtime_attaches_pack_grasp_adapter_to_profile_hints(self):
        grasp = spec_from_mapping(
            {
                "id": "grasp_flat_box_topdown_short_side_deep",
                "kind": "recovery_hint",
                "priority": 55,
                "applies_to": {"all": [{"target_name_matches": "cream_cheese|butter"}]},
                "recovery_hints": {"grasp_profile": "flat_box_topdown_short_side_deep_v1"},
            }
        )
        adapter = REPO_ROOT / "skill_packs/libero90_legacy/code/grasp_profiles.py"
        runtime = SkillRuntime([grasp], grasp_profile_registry=load_grasp_profile_registry(adapter))
        decision = runtime.force_recovery_query({"target_name": "cream_cheese_1_main"})

        params = decision["recovery_hints"]["params"]
        self.assertEqual(params[GRASP_PROFILE_ADAPTER_PARAM_KEY], str(adapter.resolve()))

    def test_runtime_expands_matching_place_profile(self):
        repair = spec_from_mapping(
            {
                "id": "book_caddy_pick_approach_recovery",
                "kind": "repair",
                "hook": "after_pi0_query",
                "priority": 65,
                "backend": "cutamp_recover",
                "trigger": {"all": [{"target_ee_distance_lt": 0.12}]},
            }
        )
        place = spec_from_mapping(
            {
                "id": "place_caddy_held_object_xy_align",
                "kind": "recovery_hint",
                "scope": "place",
                "priority": 48,
                "applies_to": {"all": [{"target_name_matches": "book"}]},
                "recovery_hints": {
                    "params": {
                        "place_profile": "caddy_book_compartment_align_budget_v1",
                        "executor": {"place_align_max_iters": 3},
                    }
                },
            }
        )
        profiles = load_place_profile_registry(index_path=REPO_ROOT / "skill_packs/libero90_legacy/skills/_index.yaml")
        runtime = SkillRuntime([repair, place], place_profile_registry=profiles)

        decision = runtime.after_pi0_query({"target_ee_distance_m": 0.08, "target_name": "black_book_1_main"})

        self.assertIsNotNone(decision)
        params = decision["recovery_hints"]["params"]
        self.assertEqual(params["place_profile"], "caddy_book_compartment_align_budget_v1")
        self.assertEqual(params["place_policy"]["profile"], "caddy_book_compartment_align_budget_v1")
        self.assertEqual(params["place_policy"]["adapter"], "libero90_legacy_place_policies")
        self.assertIn("align", params["place_policy"]["hooks"])
        self.assertIn("release", params["place_policy"]["hooks"])
        self.assertTrue(params["executor"]["place_held_object_xy_align"])
        self.assertTrue(params["executor"]["place_drop_closed_loop_align"])
        self.assertEqual(params["executor"]["place_drop_max_steps"], 80)
        self.assertEqual(params["executor"]["place_align_max_iters"], 3)

    def test_runtime_expands_matching_repair_profile(self):
        repair = spec_from_mapping(
            {
                "id": "bowl_pick_empty_close_stall",
                "kind": "repair",
                "hook": "after_pi0_query",
                "priority": 60,
                "backend": "cutamp_recover",
                "trigger": {"all": [{"aperture_lt": 0.02}]},
                "recovery_hints": {
                    "params": {
                        "repair_profile": "entry_lift_open_hand_small_v1",
                        "executor": {"recovery_entry_lift_max_steps": 20},
                    }
                },
            }
        )
        profiles = load_repair_profile_registry(REPO_ROOT / "skill_packs/libero90_legacy/profiles/repair.yaml")
        runtime = SkillRuntime([repair], repair_profile_registry=profiles)

        decision = runtime.after_pi0_query({"aperture": 0.01})

        self.assertIsNotNone(decision)
        params = decision["recovery_hints"]["params"]
        self.assertEqual(params["repair_profile"], "entry_lift_open_hand_small_v1")
        self.assertEqual(params["executor"]["recovery_entry_lift_m"], 0.045)
        self.assertEqual(params["executor"]["recovery_entry_lift_gripper_value"], 0.0)
        self.assertEqual(params["executor"]["recovery_entry_lift_max_steps"], 20)

    def test_place_policy_hook_rejects_unknown_executor_key(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            place_yaml = root / "place.yaml"
            adapter_py = root / "place_policies.py"
            place_yaml.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "name: test_place_profiles",
                        "profiles:",
                        "  bad_profile_v1:",
                        "    hooks:",
                        "      hover:",
                        "        mode: held_transfer_keep_z",
                        "        typo_executor_key: true",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            adapter_py.write_text(
                "\n".join(
                    [
                        'ADAPTER_NAME = "test_place_adapter"',
                        'PROFILE_IDS = ("bad_profile_v1",)',
                        "def resolve_hover_policy(profile, profile_data, params):",
                        '    return profile_data["hooks"]["hover"]',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            profiles = load_place_profile_registry(place_yaml, adapter_path=adapter_py)

            with self.assertRaisesRegex(SkillSchemaError, "unsupported key"):
                profiles.expand_recovery_hints({"params": {"place_profile": "bad_profile_v1"}})

    def test_runtime_expands_matching_grounding_and_geometry_profiles(self):
        repair = spec_from_mapping(
            {
                "id": "book_caddy_pick_approach_recovery",
                "kind": "repair",
                "hook": "after_pi0_query",
                "priority": 65,
                "backend": "cutamp_recover",
                "trigger": {"all": [{"target_ee_distance_lt": 0.12}]},
            }
        )
        grounding = spec_from_mapping(
            {
                "id": "desk_caddy_compartment_grounding",
                "kind": "recovery_hint",
                "scope": "grounding",
                "priority": 48,
                "applies_to": {"all": [{"target_name_matches": "book"}]},
                "recovery_hints": {"params": {"grounding_profile": "desk_caddy_compartment_v1"}},
            }
        )
        geometry = spec_from_mapping(
            {
                "id": "desk_caddy_compartment_geometry",
                "kind": "recovery_hint",
                "scope": "geometry",
                "priority": 47,
                "applies_to": {"all": [{"target_name_matches": "book"}]},
                "recovery_hints": {"params": {"geometry_profile": "desk_caddy_compartment_inner_floor_v1"}},
            }
        )
        runtime = SkillRuntime(
            [repair, grounding, geometry],
            grounding_profile_registry=load_grounding_profile_registry(
                REPO_ROOT / "skill_packs/libero90_legacy/profiles/grounding.yaml",
                adapter_path=REPO_ROOT / "skill_packs/libero90_legacy/code/grounding_profiles.py",
            ),
            geometry_profile_registry=load_geometry_profile_registry(
                REPO_ROOT / "skill_packs/libero90_legacy/profiles/geometry.yaml",
                adapter_path=REPO_ROOT / "skill_packs/libero90_legacy/code/geometry_profiles.py",
            ),
        )

        decision = runtime.after_pi0_query({"target_ee_distance_m": 0.08, "target_name": "black_book_1_main"})

        self.assertIsNotNone(decision)
        params = decision["recovery_hints"]["params"]
        self.assertEqual(params["grounding_profile"], "desk_caddy_compartment_v1")
        self.assertEqual(params["geometry_profile"], "desk_caddy_compartment_inner_floor_v1")
        self.assertEqual(
            params["grounding_hints"]["placement_surface"]["intent"],
            "container_compartment",
        )
        self.assertEqual(
            params["grounding_hints"]["placement_surface"]["planner_primitive"],
            "container_region_surface",
        )
        self.assertEqual(
            Path(params["grounding_hints"]["placement_surface"]["grounding_profile_adapter_path"]).name,
            "grounding_profiles.py",
        )
        self.assertEqual(
            params["geometry_hints"]["placement_region"]["intent"],
            "compartment_inner_floor",
        )
        self.assertEqual(
            params["geometry_hints"]["placement_region"]["planner_primitive"],
            "inner_floor",
        )
        self.assertEqual(
            Path(params["geometry_hints"]["placement_region"]["geometry_profile_adapter_path"]).name,
            "geometry_profiles.py",
        )
        self.assertEqual(params["executor"]["place_yaw_after_hover"], "world_z_thin_x")


if __name__ == "__main__":
    unittest.main()
