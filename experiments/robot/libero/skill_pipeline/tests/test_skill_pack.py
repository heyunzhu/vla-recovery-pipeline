from __future__ import annotations

import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.capabilities import load_capability_registry
from experiments.robot.libero.skill_pipeline.grasp_static import check_grasp_skill_library
from experiments.robot.libero.skill_pipeline.geometry_profiles import load_geometry_profile_registry
from experiments.robot.libero.skill_pipeline.grounding_profiles import load_grounding_profile_registry
from experiments.robot.libero.skill_pipeline.repair_profiles import load_repair_profile_registry
from experiments.robot.libero.skill_pipeline.schema import resolve_mining_skills, resolve_online_skills
from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config, resolve_skill_pack


REPO_ROOT = Path(__file__).resolve().parents[5]


class SkillPackTests(unittest.TestCase):
    def test_libero90_pack_resolves_all_registered_assets(self):
        pack = resolve_skill_pack("libero90_legacy", repo=REPO_ROOT)

        self.assertEqual(pack.name, "libero90_legacy")
        self.assertEqual(pack.skill_index, REPO_ROOT / "skill_packs/libero90_legacy/skills/_index.yaml")
        self.assertEqual(pack.capability_registry, REPO_ROOT / "skill_packs/libero90_legacy/capabilities.yaml")
        self.assertEqual(
            pack.diagnostic_signal_registry,
            REPO_ROOT / "skill_packs/libero90_legacy/diagnostics/registry.yaml",
        )
        self.assertEqual(pack.repair_profile_registry, REPO_ROOT / "skill_packs/libero90_legacy/profiles/repair.yaml")
        self.assertEqual(
            pack.place_profile_registry.resolve(),
            REPO_ROOT / "skill_packs/libero90_legacy/profiles/place.yaml",
        )
        self.assertEqual(
            pack.place_policy_adapter.resolve(),
            REPO_ROOT / "skill_packs/libero90_legacy/code/place_policies.py",
        )
        self.assertEqual(pack.grasp_profile_adapter, REPO_ROOT / "skill_packs/libero90_legacy/code/grasp_profiles.py")
        self.assertEqual(pack.grounding_profile_adapter, REPO_ROOT / "skill_packs/libero90_legacy/code/grounding_profiles.py")
        self.assertEqual(pack.geometry_profile_adapter, REPO_ROOT / "skill_packs/libero90_legacy/code/geometry_profiles.py")
        self.assertEqual(
            pack.grounding_profile_registry,
            REPO_ROOT / "skill_packs/libero90_legacy/profiles/grounding.yaml",
        )
        self.assertEqual(
            pack.geometry_profile_registry,
            REPO_ROOT / "skill_packs/libero90_legacy/profiles/geometry.yaml",
        )

        pack_ids = [spec.id for spec in resolve_online_skills(pack.skill_index)]
        self.assertGreaterEqual(len(pack_ids), 40)

        registry = load_capability_registry(index_path=pack.skill_index)
        self.assertEqual(registry.name, "libero90_legacy")
        self.assertTrue(registry.strict)

        repair = load_repair_profile_registry(index_path=pack.skill_index)
        self.assertEqual(repair.name, "libero90_legacy_repair_profiles")
        self.assertEqual(
            set(repair.profiles),
            {
                "entry_lift_escape_current_away_blocker_v1",
                "entry_lift_open_hand_mug_v1",
                "entry_lift_open_hand_small_v1",
            },
        )

        grounding = load_grounding_profile_registry(index_path=pack.skill_index)
        self.assertEqual([adapter.name for adapter in grounding.adapters], ["libero90_legacy_grounding_profiles"])
        self.assertTrue(
            {
                "bowl_stack_support_v1",
                "cabinet_top_support_v1",
                "desk_caddy_compartment_v1",
                "desk_caddy_side_table_region_v1",
                "plate_side_table_region_v1",
                "shelf_support_v1",
                "task35_mug_front_region_v1",
                "task38_plate_right_region_v1",
                "top_drawer_container_v1",
            }.issubset(set(grounding.profiles))
        )
        geometry = load_geometry_profile_registry(index_path=pack.skill_index)
        self.assertEqual([adapter.name for adapter in geometry.adapters], ["libero90_legacy_geometry_profiles"])
        self.assertTrue(
            {
                "bowl_stack_support_geometry_v1",
                "container_inside_region_geometry_v1",
                "desk_caddy_compartment_inner_floor_v1",
                "desk_caddy_side_region_geometry_v1",
                "plate_side_region_geometry_v1",
                "shelf_region_inner_floor_geometry_v1",
                "task35_mug_front_region_geometry_v1",
                "task38_plate_right_region_geometry_v1",
                "top_drawer_inner_floor_geometry_v1",
            }.issubset(set(geometry.profiles))
        )

    def test_generated_pack_uses_scratch_library(self):
        pack = resolve_skill_pack("generated_v1", repo=REPO_ROOT)

        self.assertEqual(pack.name, "generated_v1")
        self.assertEqual(pack.skills_dir, REPO_ROOT / "skill_packs/generated_v1/skills")
        self.assertEqual(pack.capability_registry, REPO_ROOT / "skill_packs/generated_v1/capabilities.yaml")
        self.assertEqual(pack.repair_profile_registry, REPO_ROOT / "skill_packs/generated_v1/profiles/repair.yaml")
        self.assertEqual(pack.place_profile_registry, REPO_ROOT / "skill_packs/generated_v1/profiles/place.yaml")
        self.assertEqual(pack.grounding_profile_registry, REPO_ROOT / "skill_packs/generated_v1/profiles/grounding.yaml")
        self.assertEqual(pack.geometry_profile_registry, REPO_ROOT / "skill_packs/generated_v1/profiles/geometry.yaml")
        self.assertIsNone(pack.place_policy_adapter)
        self.assertIsNone(pack.grasp_profile_adapter)
        self.assertIsNone(pack.grounding_profile_adapter)
        self.assertIsNone(pack.geometry_profile_adapter)
        self.assertEqual(resolve_online_skills(pack.skill_index), [])
        self.assertIn("black_bowl_plate_pick_approach_stall", [spec.id for spec in resolve_mining_skills(pack.skill_index)])
        self.assertEqual(check_grasp_skill_library(pack.skill_index).error_count, 0)

    def test_legacy_index_pack_resolves_place_profiles_and_adapter(self):
        pack = resolve_skill_pack(REPO_ROOT / "skill_packs/libero90_legacy/skills/_index.yaml", repo=REPO_ROOT)

        self.assertEqual(
            pack.place_profile_registry.resolve(),
            REPO_ROOT / "skill_packs/libero90_legacy/profiles/place.yaml",
        )
        self.assertEqual(
            pack.place_policy_adapter.resolve(),
            REPO_ROOT / "skill_packs/libero90_legacy/code/place_policies.py",
        )

    def test_resolve_skill_config_uses_explicit_pack(self):
        config = resolve_skill_config(skill_pack="libero90_legacy", repo=REPO_ROOT)

        self.assertEqual(config.skill_pack.name, "libero90_legacy")
        self.assertEqual(config.skill_index, REPO_ROOT / "skill_packs/libero90_legacy/skills/_index.yaml")
        self.assertEqual(config.skills_dir, REPO_ROOT / "skill_packs/libero90_legacy/skills")

    def test_explicit_index_overrides_pack_registry_default(self):
        config = resolve_skill_config(
            skill_pack="generated_v1",
            skill_index="skill_packs/libero90_legacy/skills/_index.yaml",
            repo=REPO_ROOT,
        )

        self.assertEqual(config.skill_pack.name, "generated_v1")
        self.assertEqual(config.skill_index, REPO_ROOT / "skill_packs/libero90_legacy/skills/_index.yaml")
        self.assertEqual(config.skills_dir, REPO_ROOT / "skill_packs/libero90_legacy/skills")
        self.assertEqual(config.capability_registry, REPO_ROOT / "skill_packs/generated_v1/capabilities.yaml")
        self.assertEqual(config.repair_profile_registry, REPO_ROOT / "skill_packs/generated_v1/profiles/repair.yaml")
        self.assertEqual(config.place_profile_registry, REPO_ROOT / "skill_packs/generated_v1/profiles/place.yaml")
        self.assertEqual(
            config.place_policy_adapter.resolve(),
            REPO_ROOT / "skill_packs/libero90_legacy/code/place_policies.py",
        )
        self.assertEqual(config.grounding_profile_registry, REPO_ROOT / "skill_packs/generated_v1/profiles/grounding.yaml")
        self.assertEqual(config.geometry_profile_registry, REPO_ROOT / "skill_packs/generated_v1/profiles/geometry.yaml")


if __name__ == "__main__":
    unittest.main()
