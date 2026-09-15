"""Runtime auto-discovery of pack-authored code adapters.

A skill pack may ship code under ``<pack>/code/``.  The engine finds it without
an explicit ``*_adapter`` key in ``skills/_index.yaml`` as long as the file
declares a non-empty id list (``PROFILE_IDS`` / ``PREDICATE_IDS``).  These tests
pin that behaviour, the loud failure when code ships without a profile catalog,
and the fact that real packs keep working through their explicit declarations.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.robot.libero.skill_pipeline.geometry_profiles import load_geometry_profile_registry
from experiments.robot.libero.skill_pipeline.grounding_profiles import load_grounding_profile_registry
from experiments.robot.libero.skill_pipeline.place_profiles import load_place_profile_registry
from experiments.robot.libero.skill_pipeline.predicate_registry import load_predicate_registry
from experiments.robot.libero.skill_pipeline.runtime import SkillRuntime
from experiments.robot.libero.skill_pipeline.schema import SkillSchemaError
from experiments.robot.libero.tiptop_repro.grasp_profiles import (
    GRASP_PROFILE_ADAPTER_PARAM_KEY,
    load_grasp_profile_registry,
    profile_gripper_width,
    sample_grasp_profile,
)


REPO_ROOT = Path(__file__).resolve().parents[5]

GEOMETRY_CODE = '''\
ADAPTER_NAME = "vfy_geometry"
PROFILE_IDS = ("vfy_geom",)


def normalize_geometry_profile_params(profile, params):
    out = dict(params)
    out["vfy_geometry_adapter_applied"] = profile
    return out
'''

GROUNDING_CODE = '''\
ADAPTER_NAME = "vfy_grounding"
PROFILE_IDS = ("vfy_ground",)


def normalize_grounding_profile_params(profile, params):
    out = dict(params)
    out["vfy_grounding_adapter_applied"] = profile
    return out
'''

PLACE_CODE = '''\
ADAPTER_NAME = "vfy_place"
PROFILE_IDS = ("vfy_place",)


def resolve_hover_policy(profile, profile_data, params):
    return {"mode": "executor_options", "executor": {"held_transfer_keep_z": True}}
'''

PREDICATE_CODE = '''\
ADAPTER_NAME = "vfy_predicates"
PREDICATE_IDS = ("vfy_pred",)
APPLIES_PREDICATE_IDS = ("vfy_applies",)


def evaluate_predicate(name, expected, state):
    if name != "vfy_pred":
        raise KeyError(name)
    return bool(state.get("vfy_value", False)) == bool(expected)


def evaluate_applies_predicate(name, expected, state):
    if name != "vfy_applies":
        raise KeyError(name)
    return bool(state.get("vfy_value", False)) == bool(expected)


def actual_value_for_predicate(name, state):
    return state.get("vfy_value")
'''

GRASP_CODE = '''\
ADAPTER_NAME = "vfy_grasp"
PROFILE_IDS = ("vfy_grasp",)


def sample_grasp_profile(profile, dims, *, rim=False, pose=None, **kwargs):
    return [{"profile": profile, "rim": bool(rim)}]


def profile_gripper_width(profile, dims, *, rim=False, radius=None, pose=None, **kwargs):
    return 0.042
'''

SCAFFOLD_GEOMETRY_CODE = '''\
"""Scaffold template: fill PROFILE_IDS once a geometry profile is authored."""
PROFILE_IDS = ()


def normalize_geometry_profile_params(profile, params):
    raise NotImplementedError
'''

CODE_FILES = {
    "geometry_profiles.py": GEOMETRY_CODE,
    "grounding_profiles.py": GROUNDING_CODE,
    "place_policies.py": PLACE_CODE,
    "predicates.py": PREDICATE_CODE,
    "grasp_profiles.py": GRASP_CODE,
}

HINT_SKILL = """---
id: vfy_hints
name: Verify pack-authored adapters
kind: recovery_hint
track: pair
scope: grasp
priority: 45
when_to_apply: Test fixture for pack-authored code discovery.
when_not_to_apply: Never in a real run.
failure_signature:
  - Fixture only.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - vfy_applies: true
recovery_hints:
  grasp_profile: vfy_grasp
  params:
    geometry_profile: vfy_geom
    grounding_profile: vfy_ground
    place_profile: vfy_place
evidence:
  tasks:
    - fixture
  episodes:
    - fixture
---

## Intent

Test fixture for pack-authored code discovery.
"""

CAPABILITIES = {
    "schema_version": 1,
    "name": "vfy_capabilities",
    "mode": "strict",
    "capabilities": {
        "grasp_profiles": ["vfy_grasp"],
        "place_profiles": ["vfy_place"],
        "repair_profiles": [],
        "grounding_profiles": ["vfy_ground"],
        "geometry_profiles": ["vfy_geom"],
        "geometry_hint_keys": [],
        "geometry_hint_intents": [],
        "geometry_descriptor_shapes": [],
        "grounding_hint_keys": [],
        "grounding_hint_intents": [],
        "executor_options": ["held_transfer_keep_z"],
        "place_candidate_policies": [],
        "place_yaw_policies": [],
        "release_modes": [],
    },
}


def _write_pack(
    root: Path,
    *,
    catalogs: dict[str, dict] | None = None,
    code: dict[str, str] | None = None,
    index_extra: dict | None = None,
) -> Path:
    """Create ``<root>/skills/_index.yaml`` plus optional catalogs and code."""
    (root / "skills").mkdir(parents=True)
    index = {"name": root.name, "online": [], "fail_only": []}
    index.update(index_extra or {})
    (root / "skills" / "_index.yaml").write_text(json.dumps(index), encoding="utf-8")
    if catalogs:
        (root / "profiles").mkdir()
        for filename, profiles in catalogs.items():
            body = {"name": f"{root.name}_{Path(filename).stem}_catalog", "profiles": profiles}
            (root / "profiles" / filename).write_text(json.dumps(body), encoding="utf-8")
    if code:
        (root / "code").mkdir()
        for filename, text in code.items():
            (root / "code" / filename).write_text(text, encoding="utf-8")
    return root / "skills" / "_index.yaml"


class AdapterDiscoveryTests(unittest.TestCase):
    def test_pack_code_discovered_from_inferred_layout(self):
        """No ``*_adapter`` key: every adapter type is found from ``code/`` alone."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            index = _write_pack(
                Path(td) / "pack_full",
                catalogs={
                    "geometry.yaml": {"vfy_geom": {"params": {}}, "plain_geom": {"params": {}}},
                    "grounding.yaml": {"vfy_ground": {"params": {}}},
                    "place.yaml": {"vfy_place": {"params": {}, "hooks": {}}},
                },
                code=dict(CODE_FILES),
            )

            geometry = load_geometry_profile_registry(index_path=index)
            self.assertTrue(geometry.enabled)
            self.assertEqual(
                geometry.expand_recovery_hints({"params": {"geometry_profile": "vfy_geom"}})["params"][
                    "vfy_geometry_adapter_applied"
                ],
                "vfy_geom",
            )
            # A catalog entry no adapter claims stays a plain profile.
            self.assertEqual(
                sorted(geometry.expand_recovery_hints({"params": {"geometry_profile": "plain_geom"}})["params"]),
                ["geometry_profile"],
            )

            grounding = load_grounding_profile_registry(index_path=index)
            self.assertEqual(
                grounding.expand_recovery_hints({"params": {"grounding_profile": "vfy_ground"}})["params"][
                    "vfy_grounding_adapter_applied"
                ],
                "vfy_ground",
            )

            place = load_place_profile_registry(index_path=index)
            params = place.expand_recovery_hints({"params": {"place_profile": "vfy_place"}})["params"]
            self.assertEqual(params["place_policy"]["adapter"], "vfy_place")
            self.assertTrue(params["executor"]["held_transfer_keep_z"])

            predicates = load_predicate_registry(index_path=index)
            self.assertIn("vfy_pred", predicates.trigger_predicate_ids)
            self.assertIn("vfy_applies", predicates.applies_predicate_ids)
            self.assertTrue(predicates.evaluate_predicate("vfy_pred", True, {"vfy_value": True}))

            grasp = load_grasp_profile_registry(index_path=index)
            self.assertIn("vfy_grasp", grasp.profile_ids)
            self.assertEqual(
                sample_grasp_profile("vfy_grasp", (0.1, 0.1, 0.1), rim=False, registry=grasp),
                [{"profile": "vfy_grasp", "rim": False}],
            )
            self.assertEqual(profile_gripper_width("vfy_grasp", (0.1, 0.1, 0.1), registry=grasp), 0.042)

    def test_code_without_catalog_rejects_profile_reference(self):
        """Code without a catalog loads, but naming a profile fails loudly."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            index = _write_pack(Path(td) / "pack_codeonly", code=dict(CODE_FILES))

            geometry = load_geometry_profile_registry(index_path=index)
            self.assertTrue(geometry.enabled)
            self.assertEqual(geometry.profiles, {})
            with self.assertRaises(SkillSchemaError) as ctx:
                geometry.expand_recovery_hints({"params": {"geometry_profile": "vfy_geom"}})
            self.assertIn("unknown geometry_profile", str(ctx.exception))

            with self.assertRaises(SkillSchemaError):
                load_grounding_profile_registry(index_path=index).expand_recovery_hints(
                    {"params": {"grounding_profile": "vfy_ground"}}
                )
            with self.assertRaises(SkillSchemaError):
                load_place_profile_registry(index_path=index).expand_recovery_hints(
                    {"params": {"place_profile": "vfy_place"}}
                )

    def test_empty_scaffold_is_ignored(self):
        """A scaffold with no declared ids is skipped and leaves the registry off."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            index = _write_pack(
                Path(td) / "pack_scaffold",
                code={"geometry_profiles.py": SCAFFOLD_GEOMETRY_CODE},
            )
            geometry = load_geometry_profile_registry(index_path=index)
            self.assertFalse(geometry.enabled)
            self.assertEqual(
                geometry.expand_recovery_hints({"params": {"geometry_profile": "whatever"}})["params"],
                {"geometry_profile": "whatever"},
            )

    def test_explicit_and_inferred_adapter_loaded_once(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td) / "pack_explicit"
            index = _write_pack(
                root,
                catalogs={"geometry.yaml": {"vfy_geom": {"params": {}}}},
                code={"geometry_profiles.py": GEOMETRY_CODE},
                index_extra={
                    "geometry_profile_registry": "../profiles/geometry.yaml",
                    "geometry_profile_adapter": "../code/geometry_profiles.py",
                },
            )
            geometry = load_geometry_profile_registry(index_path=index)
            self.assertEqual(
                [adapter.path for adapter in geometry.adapters],
                [str((root / "code" / "geometry_profiles.py").resolve())],
            )

    def test_runtime_applies_inferred_pack_code(self):
        """End to end: a pack predicate gates a pack hint whose profiles are pack code."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td) / "pack_runtime"
            index = _write_pack(
                root,
                catalogs={
                    "geometry.yaml": {"vfy_geom": {"params": {}}},
                    "grounding.yaml": {"vfy_ground": {"params": {}}},
                    "place.yaml": {"vfy_place": {"params": {}, "hooks": {}}},
                },
                code=dict(CODE_FILES),
                index_extra={
                    "capability_registry": "../capabilities.yaml",
                    "online": ["pair/recovery_hint/vfy_hints.md"],
                },
            )
            (root / "capabilities.yaml").write_text(json.dumps(CAPABILITIES), encoding="utf-8")
            hint_dir = root / "skills" / "pair" / "recovery_hint"
            hint_dir.mkdir(parents=True)
            (hint_dir / "vfy_hints.md").write_text(HINT_SKILL, encoding="utf-8")

            runtime = SkillRuntime.from_index(index)
            self.assertEqual(len(runtime.skills), 1)
            params = runtime.force_recovery_query({"vfy_value": True})["recovery_hints"]["params"]
            self.assertEqual(params["vfy_geometry_adapter_applied"], "vfy_geom")
            self.assertEqual(params["vfy_grounding_adapter_applied"], "vfy_ground")
            self.assertEqual(params["place_policy"]["adapter"], "vfy_place")
            self.assertEqual(
                params[GRASP_PROFILE_ADAPTER_PARAM_KEY],
                str((root / "code" / "grasp_profiles.py").resolve()),
            )

    def test_libero90_legacy_explicit_adapters_unchanged(self):
        """The real pack declares its adapters; inference must not duplicate them."""
        index = REPO_ROOT / "skill_packs/libero90_legacy/skills/_index.yaml"
        geometry = load_geometry_profile_registry(index_path=index)
        grounding = load_grounding_profile_registry(index_path=index)
        place = load_place_profile_registry(index_path=index)
        grasp = load_grasp_profile_registry(index_path=index)

        self.assertEqual(len(geometry.adapters), 1)
        self.assertEqual(len(grounding.adapters), 1)
        self.assertEqual(len(place.adapters), 1)
        self.assertEqual(len(grasp.adapters), 1)
        self.assertEqual(len(geometry.profiles), 9)
        self.assertEqual(len(grounding.profiles), 9)
        self.assertEqual(len(place.profiles), 2)
        self.assertEqual(len(grasp.adapters[0].profile_ids), 25)
        self.assertTrue(
            all(adapter.path.endswith(".py") for adapter in (*geometry.adapters, *grounding.adapters, *place.adapters))
        )


if __name__ == "__main__":
    unittest.main()
