from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.code_admission import CodeAdmissionConfig, run_code_admission


ALL_CAPABILITY_KEYS = (
    "grasp_profiles",
    "place_profiles",
    "repair_profiles",
    "grounding_profiles",
    "geometry_profiles",
    "geometry_hint_keys",
    "geometry_hint_intents",
    "grounding_hint_keys",
    "grounding_hint_intents",
    "executor_options",
    "place_candidate_policies",
    "place_yaw_policies",
    "release_modes",
)


def _write_registry(
    path: Path,
    *,
    grasp_profiles: list[str],
    place_profiles: list[str] | None = None,
    grounding_profiles: list[str] | None = None,
    geometry_profiles: list[str] | None = None,
) -> None:
    place_profiles = place_profiles or []
    grounding_profiles = grounding_profiles or []
    geometry_profiles = geometry_profiles or []
    body = [
        "schema_version: 1",
        "name: test_generated",
        "mode: strict",
        "capabilities:",
    ]
    for key in ALL_CAPABILITY_KEYS:
        if key == "grasp_profiles":
            values = grasp_profiles
        elif key == "place_profiles":
            values = place_profiles
        elif key == "grounding_profiles":
            values = grounding_profiles
        elif key == "geometry_profiles":
            values = geometry_profiles
        else:
            values = []
        if values:
            body.append(f"  {key}:")
            body.extend(f"    - {item}" for item in values)
        else:
            body.append(f"  {key}: []")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def _write_skill(path: Path, profile: str = "bowl_rim_diagonal_mixed_topdown_v1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                "id: test_grasp_hint",
                "name: Test grasp hint",
                "kind: recovery_hint",
                "track: fail_only",
                "scope: grasp",
                "priority: 10",
                "when_to_apply: test",
                "when_not_to_apply: test",
                "failure_signature:",
                "  - test",
                "recovery_point: after repair trigger",
                "applies_to:",
                "  all:",
                "    - target_name_matches: bowl",
                "recovery_hints:",
                f"  grasp_profile: {profile}",
                "  target: target",
                "evidence:",
                "  tasks: []",
                "  episodes: []",
                "---",
                "",
                "Test.",
            ]
        ),
        encoding="utf-8",
    )


class CodeAdmissionTests(unittest.TestCase):
    def test_rejects_code_change_outside_declared_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_capabilities" / "generated_scratch_v1.yaml"
            _write_registry(registry, grasp_profiles=[])
            manifest = root / "manifest.yaml"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - grasp_profile",
                        "touched_files:",
                        "  - experiments/robot/libero/skill_pipeline/runner.py",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    capability_registry=registry,
                    changed_files=["experiments/robot/libero/skill_pipeline/runner.py"],
                )
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("outside declared" in item for item in report["errors"]))

    def test_allows_pack_local_skill_markdown_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_packs" / "generated_v1" / "capabilities.yaml"
            _write_registry(registry, grasp_profiles=[])
            manifest = root / "manifest.yaml"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - skill_markdown",
                        "touched_files:",
                        "  - skill_packs/generated_v1/skills/fail_only/repair/generated_stall.md",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    capability_registry=registry,
                    changed_files=["skill_packs/generated_v1/skills/fail_only/repair/generated_stall.md"],
                )
            )

            self.assertTrue(report["ok"], report)

    def test_rejects_added_grasp_profile_that_is_not_registered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_capabilities" / "generated_scratch_v1.yaml"
            _write_registry(registry, grasp_profiles=[])
            manifest = root / "manifest.yaml"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - grasp_profile",
                        "new_capabilities:",
                        "  grasp_profiles:",
                        "    - bowl_rim_diagonal_mixed_topdown_v1",
                        "touched_files:",
                        "  - skill_packs/generated_v1/code/grasp_profiles.py",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    capability_registry=registry,
                    changed_files=["skill_packs/generated_v1/code/grasp_profiles.py"],
                    base_file_texts={"skill_packs/generated_v1/code/grasp_profiles.py": "profiles = []\n"},
                    current_file_texts={
                        "skill_packs/generated_v1/code/grasp_profiles.py": (
                            'profiles = ["bowl_rim_diagonal_mixed_topdown_v1"]\n'
                        )
                    },
                )
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("not registered" in item for item in report["errors"]))

    def test_rejects_added_geometry_profile_that_is_not_registered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_capabilities" / "generated_scratch_v1.yaml"
            _write_registry(registry, grasp_profiles=[], geometry_profiles=[])
            manifest = root / "manifest.yaml"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - geometry_hint",
                        "new_capabilities:",
                        "  geometry_profiles:",
                        "    - generated_container_inner_floor_v1",
                        "touched_files:",
                        "  - skill_packs/generated_v1/code/geometry_profiles.py",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    capability_registry=registry,
                    changed_files=["skill_packs/generated_v1/code/geometry_profiles.py"],
                    base_file_texts={"skill_packs/generated_v1/code/geometry_profiles.py": "PROFILE_IDS = []\n"},
                    current_file_texts={
                        "skill_packs/generated_v1/code/geometry_profiles.py": (
                            'PROFILE_IDS = ["generated_container_inner_floor_v1"]\n'
                        )
                    },
                )
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("added geometry profile is not registered" in item for item in report["errors"]))

    def test_rejects_added_grounding_profile_that_is_not_registered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_capabilities" / "generated_scratch_v1.yaml"
            _write_registry(registry, grasp_profiles=[], grounding_profiles=[])
            manifest = root / "manifest.yaml"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - grounding_hint",
                        "new_capabilities:",
                        "  grounding_profiles:",
                        "    - generated_table_region_v1",
                        "touched_files:",
                        "  - skill_packs/generated_v1/code/grounding_profiles.py",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    capability_registry=registry,
                    changed_files=["skill_packs/generated_v1/code/grounding_profiles.py"],
                    base_file_texts={"skill_packs/generated_v1/code/grounding_profiles.py": "PROFILE_IDS = []\n"},
                    current_file_texts={
                        "skill_packs/generated_v1/code/grounding_profiles.py": (
                            'PROFILE_IDS = ["generated_table_region_v1"]\n'
                        )
                    },
                )
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("added grounding profile is not registered" in item for item in report["errors"]))

    def test_passes_registered_existing_grasp_profile_patch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_capabilities" / "generated_scratch_v1.yaml"
            _write_registry(registry, grasp_profiles=["bowl_rim_diagonal_mixed_topdown_v1"])
            skill = root / "draft.md"
            _write_skill(skill)
            manifest = root / "manifest.yaml"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - grasp_profile",
                        "new_capabilities:",
                        "  grasp_profiles:",
                        "    - bowl_rim_diagonal_mixed_topdown_v1",
                        "touched_files:",
                        "  - skill_packs/generated_v1/code/grasp_profiles.py",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    skill_files=[skill],
                    capability_registry=registry,
                    changed_files=["skill_packs/generated_v1/code/grasp_profiles.py"],
                    base_file_texts={"skill_packs/generated_v1/code/grasp_profiles.py": "profiles = []\n"},
                    current_file_texts={
                        "skill_packs/generated_v1/code/grasp_profiles.py": (
                            'profiles = ["bowl_rim_diagonal_mixed_topdown_v1"]\n'
                        )
                    },
                )
            )

            self.assertTrue(report["ok"], report)
            self.assertEqual(report["code_added_capabilities"]["grasp_profiles"], ["bowl_rim_diagonal_mixed_topdown_v1"])

    def test_passes_registered_existing_geometry_profile_patch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_capabilities" / "generated_scratch_v1.yaml"
            _write_registry(
                registry,
                grasp_profiles=[],
                geometry_profiles=["generated_container_inner_floor_v1"],
            )
            manifest = root / "manifest.yaml"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - geometry_hint",
                        "new_capabilities:",
                        "  geometry_profiles:",
                        "    - generated_container_inner_floor_v1",
                        "touched_files:",
                        "  - skill_packs/generated_v1/code/geometry_profiles.py",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    capability_registry=registry,
                    changed_files=["skill_packs/generated_v1/code/geometry_profiles.py"],
                    base_file_texts={"skill_packs/generated_v1/code/geometry_profiles.py": "PROFILE_IDS = []\n"},
                    current_file_texts={
                        "skill_packs/generated_v1/code/geometry_profiles.py": (
                            'PROFILE_IDS = ["generated_container_inner_floor_v1"]\n'
                        )
                    },
                )
            )

            self.assertTrue(report["ok"], report)
            self.assertEqual(
                report["code_added_capabilities"]["geometry_profiles"],
                ["generated_container_inner_floor_v1"],
            )

    def test_passes_registered_existing_grounding_profile_patch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_capabilities" / "generated_scratch_v1.yaml"
            _write_registry(
                registry,
                grasp_profiles=[],
                grounding_profiles=["generated_table_region_v1"],
            )
            manifest = root / "manifest.yaml"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - grounding_hint",
                        "new_capabilities:",
                        "  grounding_profiles:",
                        "    - generated_table_region_v1",
                        "touched_files:",
                        "  - skill_packs/generated_v1/code/grounding_profiles.py",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    capability_registry=registry,
                    changed_files=["skill_packs/generated_v1/code/grounding_profiles.py"],
                    base_file_texts={"skill_packs/generated_v1/code/grounding_profiles.py": "PROFILE_IDS = []\n"},
                    current_file_texts={
                        "skill_packs/generated_v1/code/grounding_profiles.py": (
                            'PROFILE_IDS = ["generated_table_region_v1"]\n'
                        )
                    },
                )
            )

            self.assertTrue(report["ok"], report)
            self.assertEqual(
                report["code_added_capabilities"]["grounding_profiles"],
                ["generated_table_region_v1"],
            )

    def test_allows_dynamic_pack_local_grounding_profile_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "skill_packs" / "custom_pack"
            registry = pack / "capabilities.yaml"
            _write_registry(
                registry,
                grasp_profiles=[],
                grounding_profiles=["generated_table_region_v1"],
            )
            manifest = root / "manifest.yaml"
            rel = "skill_packs/custom_pack/code/grounding_profiles.py"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - grounding_hint",
                        "new_capabilities:",
                        "  grounding_profiles:",
                        "    - generated_table_region_v1",
                        "touched_files:",
                        f"  - {rel}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    capability_registry=registry,
                    pack_root=pack,
                    changed_files=[rel],
                    base_file_texts={rel: "PROFILE_IDS = []\n"},
                    current_file_texts={rel: 'PROFILE_IDS = ["generated_table_region_v1"]\n'},
                )
            )

            self.assertTrue(report["ok"], report)
            self.assertIn("skill_packs/custom_pack/code/", report["boundary"]["allowed_prefixes"])
            self.assertEqual(
                report["code_added_capabilities"]["grounding_profiles"],
                ["generated_table_region_v1"],
            )

    def test_pack_local_place_policy_code_allowed_and_registered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "skill_packs" / "custom_pack"
            registry = pack / "capabilities.yaml"
            _write_registry(
                registry,
                grasp_profiles=[],
                place_profiles=["generated_place_budget_v1"],
            )
            manifest = root / "manifest.yaml"
            rel = "skill_packs/custom_pack/code/place_policies.py"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - place_policy",
                        "new_capabilities:",
                        "  place_profiles:",
                        "    - generated_place_budget_v1",
                        "touched_files:",
                        f"  - {rel}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    capability_registry=registry,
                    pack_root=pack,
                    changed_files=[rel],
                    base_file_texts={rel: ""},
                    current_file_texts={rel: 'PROFILE_IDS = ("generated_place_budget_v1",)\n'},
                )
            )

            self.assertTrue(report["ok"], report)
            self.assertIn("skill_packs/custom_pack/code/", report["boundary"]["allowed_prefixes"])

    def test_rejects_skill_reference_to_unregistered_capability(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_capabilities" / "generated_scratch_v1.yaml"
            _write_registry(registry, grasp_profiles=[])
            skill = root / "draft.md"
            _write_skill(skill)

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    skill_files=[skill],
                    capability_registry=registry,
                    changed_files=[],
                )
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("bowl_rim_diagonal_mixed_topdown_v1" in item for item in report["errors"]))

    def test_rejects_registry_change_without_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_capabilities" / "generated_scratch_v1.yaml"
            _write_registry(registry, grasp_profiles=[])

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    capability_registry=registry,
                    changed_files=["skill_capabilities/generated_scratch_v1.yaml"],
                )
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("registry changes require" in item for item in report["errors"]))

    def test_rejects_pack_registry_change_without_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "skill_packs" / "generated_v1" / "capabilities.yaml"
            _write_registry(registry, grasp_profiles=[])

            report = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root,
                    out_dir=root / "out",
                    capability_registry=registry,
                    changed_files=["skill_packs/generated_v1/capabilities.yaml"],
                )
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("registry changes require" in item for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
