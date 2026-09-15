from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.capabilities import load_capability_registry
from experiments.robot.libero.skill_pipeline.predicate_registry import load_predicate_registry
from experiments.robot.libero.skill_pipeline.runtime import SkillRuntime
from experiments.robot.libero.skill_pipeline.schema import (
    SkillSchemaError,
    load_skill,
    resolve_online_skills,
    spec_from_mapping,
)


REPO_ROOT = Path(__file__).resolve().parents[5]
LEGACY_INDEX = REPO_ROOT / "skill_packs" / "libero90_legacy" / "skills" / "_index.yaml"
SCRATCH_INDEX = REPO_ROOT / "skill_packs" / "generated_v1" / "skills" / "_index.yaml"
CORE_REGISTRY = REPO_ROOT / "skill_capabilities" / "core_minimal.yaml"


class CapabilityRegistryTests(unittest.TestCase):
    def test_registry_rejects_declared_executor_option_without_engine_consumer(self):
        with tempfile.TemporaryDirectory() as tmp:
            predicate_registry_path = Path(tmp) / "predicates.yaml"
            predicate_registry_path.write_text(
                "schema_version: 1\n"
                "name: tiny_predicates\n"
                "predicates:\n"
                "  trigger:\n"
                "    wrong_intent_diag:\n"
                "      source: diagnostic_signal\n"
                "      signal: wrong_intent_score\n"
                "      op: gt\n"
                "      evidence_role: failure_evidence\n",
                encoding="utf-8",
            )
            predicate_registry = load_predicate_registry(predicate_registry_path)
            registry_path = Path(tmp) / "capabilities.yaml"
            registry_path.write_text(
                "schema_version: 1\n"
                "name: bad_registry\n"
                "mode: strict\n"
                "capabilities:\n"
                "  executor_options:\n"
                "    - teleport_to_grasp\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SkillSchemaError, "not consumed by engine"):
                load_capability_registry(registry_path)

    def test_core_minimal_rejects_unregistered_bowl_grasp_profile(self):
        registry = load_capability_registry(CORE_REGISTRY)
        spec = spec_from_mapping(
            {
                "id": "unregistered_bowl_hint",
                "kind": "recovery_hint",
                "scope": "grasp",
                "applies_to": {"all": [{"target_name_matches": "bowl"}]},
                "recovery_hints": {
                    "grasp_profile": "bowl_rim_diagonal_mixed_topdown_v1",
                },
            }
        )

        audit = registry.audit_skill(spec)

        self.assertFalse(audit.ok)
        self.assertIn("grasp_profiles", audit.used)
        self.assertTrue(any("bowl_rim_diagonal_mixed_topdown_v1" in item for item in audit.errors))

    def test_core_minimal_rejects_unregistered_place_profile(self):
        registry = load_capability_registry(CORE_REGISTRY)
        spec = spec_from_mapping(
            {
                "id": "unregistered_place_hint",
                "kind": "recovery_hint",
                "scope": "place",
                "applies_to": {"all": [{"target_name_matches": "book"}]},
                "recovery_hints": {
                    "params": {"place_profile": "caddy_book_compartment_align_budget_v1"},
                },
            }
        )

        audit = registry.audit_skill(spec)

        self.assertFalse(audit.ok)
        self.assertEqual(audit.used["place_profiles"], ["caddy_book_compartment_align_budget_v1"])
        self.assertTrue(any("caddy_book_compartment_align_budget_v1" in item for item in audit.errors))

    def test_core_minimal_rejects_unregistered_repair_profile(self):
        registry = load_capability_registry(CORE_REGISTRY)
        spec = spec_from_mapping(
            {
                "id": "unregistered_repair_entry",
                "kind": "repair",
                "hook": "after_pi0_query",
                "backend": "cutamp_recover",
                "trigger": {"all": [{"ee_stalled": True}]},
                "recovery_hints": {
                    "params": {"repair_profile": "entry_lift_open_hand_small_v1"},
                },
            }
        )

        audit = registry.audit_skill(spec)

        self.assertFalse(audit.ok)
        self.assertEqual(audit.used["repair_profiles"], ["entry_lift_open_hand_small_v1"])
        self.assertTrue(any("entry_lift_open_hand_small_v1" in item for item in audit.errors))

    def test_strict_registry_gates_custom_predicates_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            predicate_registry_path = Path(tmp) / "predicates.yaml"
            predicate_registry_path.write_text(
                "schema_version: 1\n"
                "name: tiny_predicates\n"
                "predicates:\n"
                "  trigger:\n"
                "    wrong_intent_diag:\n"
                "      source: diagnostic_signal\n"
                "      signal: wrong_intent_score\n"
                "      op: gt\n"
                "      evidence_role: failure_evidence\n",
                encoding="utf-8",
            )
            predicate_registry = load_predicate_registry(predicate_registry_path)
            registry_path = Path(tmp) / "capabilities.yaml"
            registry_path.write_text(
                "schema_version: 1\n"
                "name: tiny_registry\n"
                "mode: strict\n"
                "capabilities:\n"
                "  trigger_predicates:\n"
                "    - wrong_intent_diag\n"
                "  diagnostic_signals:\n"
                "    - wrong_intent_score\n",
                encoding="utf-8",
            )
            registry = load_capability_registry(registry_path)
            spec = spec_from_mapping(
                {
                    "id": "custom_predicate_repair",
                    "kind": "repair",
                    "hook": "after_pi0_query",
                    "backend": "cutamp_recover",
                    "trigger": {
                        "all": [
                            {"wrong_intent_diag": True},
                            {"diagnostic_signal_gt": {"signal": "wrong_intent_score", "value": 0.4}},
                        ]
                    },
                },
                predicate_registry=predicate_registry,
            )

            audit = registry.audit_skill(spec)

        self.assertTrue(audit.ok)
        self.assertEqual(audit.used["trigger_predicates"], ["wrong_intent_diag"])
        self.assertEqual(audit.used["diagnostic_signals"], ["wrong_intent_score"])

    def test_strict_registry_rejects_unregistered_custom_predicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            predicate_registry_path = Path(tmp) / "predicates.yaml"
            predicate_registry_path.write_text(
                "schema_version: 1\n"
                "name: tiny_predicates\n"
                "predicates:\n"
                "  trigger:\n"
                "    wrong_intent_diag:\n"
                "      source: diagnostic_signal\n"
                "      signal: wrong_intent_score\n"
                "      op: gt\n"
                "      evidence_role: failure_evidence\n",
                encoding="utf-8",
            )
            predicate_registry = load_predicate_registry(predicate_registry_path)
            registry_path = Path(tmp) / "capabilities.yaml"
            registry_path.write_text(
                "schema_version: 1\n"
                "name: tiny_registry\n"
                "mode: strict\n"
                "capabilities:\n"
                "  diagnostic_signals:\n"
                "    - wrong_intent_score\n",
                encoding="utf-8",
            )
            registry = load_capability_registry(registry_path)
            spec = spec_from_mapping(
                {
                    "id": "custom_predicate_repair",
                    "kind": "repair",
                    "hook": "after_pi0_query",
                    "backend": "cutamp_recover",
                    "trigger": {
                        "all": [
                            {"wrong_intent_diag": True},
                            {"diagnostic_signal_gt": {"signal": "wrong_intent_score", "value": 0.4}},
                        ]
                    },
                },
                predicate_registry=predicate_registry,
            )

            audit = registry.audit_skill(spec)

        self.assertFalse(audit.ok)
        self.assertTrue(any("wrong_intent_diag" in item for item in audit.errors))

    def test_scratch_index_declares_its_current_legacy_bowl_dependency(self):
        registry = load_capability_registry(index_path=SCRATCH_INDEX)
        scratch_skill = load_skill(
            REPO_ROOT
            / "skill_packs"
            / "generated_v1"
            / "skills"
            / "fail_only"
            / "trigger"
            / "black_bowl_plate_pick_approach_stall.md"
        )

        audit = registry.audit_skill(scratch_skill)

        self.assertTrue(audit.ok)
        self.assertEqual(audit.used["grasp_profiles"], ["bowl_rim_diagonal_mixed_topdown_v1"])

    def test_legacy_registry_allows_online_library_capabilities(self):
        registry = load_capability_registry(index_path=LEGACY_INDEX)
        specs = resolve_online_skills(LEGACY_INDEX)
        errors: list[str] = []

        for spec in specs:
            audit = registry.audit_skill(spec)
            errors.extend(f"{spec.id}: {item}" for item in audit.errors)

        self.assertEqual(errors, [])

    def test_runtime_rejects_merged_unregistered_hint(self):
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
        registry = load_capability_registry(CORE_REGISTRY)
        runtime = SkillRuntime([repair, grasp], capability_registry=registry)

        with self.assertRaises(SkillSchemaError):
            runtime.after_pi0_query(
                {
                    "aperture": 0.01,
                    "target_name": "akita_black_bowl_1_main",
                }
            )


if __name__ == "__main__":
    unittest.main()
