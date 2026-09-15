"""Pack code self-check: protocol, catalog sync, determinism, side effects.

The check runs on the pack code a manifest changed, before a GPU validation
round, and its errors gate code admission.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.robot.libero.skill_pipeline.code_admission import (
    CodeAdmissionConfig,
    _pack_code_check_files,
    run_code_admission,
    run_pack_code_admission_check,
)
from experiments.robot.libero.skill_pipeline.pack_code_check import (
    check_pack_code,
    check_pack_code_file,
)


REPO_ROOT = Path(__file__).resolve().parents[5]

NON_DETERMINISTIC = """\
PROFILE_IDS = ("g1",)
_calls = {"n": 0}


def sample_grasp_profile(profile, dims, *, rim=False, pose=None):
    _calls["n"] += 1
    return [{"n": _calls["n"]}]


def profile_gripper_width(profile, dims, *, rim=False, radius=None, pose=None):
    return 0.04
"""

FORBIDDEN_IMPORT = """\
import random

PROFILE_IDS = ("g1",)


def normalize_geometry_profile_params(profile, params):
    return dict(params)
"""

CATALOG_MISMATCH = """\
PROFILE_IDS = ("in_catalog", "not_in_catalog")


def normalize_geometry_profile_params(profile, params):
    return dict(params)
"""

SCAFFOLD = """\
PROFILE_IDS = ()


def normalize_geometry_profile_params(profile, params):
    raise NotImplementedError
"""


def _write_pack(root: Path, files: dict[str, str], catalogs: dict[str, dict] | None = None) -> Path:
    (root / "skills").mkdir(parents=True)
    (root / "skills" / "_index.yaml").write_text(
        json.dumps({"name": root.name, "online": [], "fail_only": []}), encoding="utf-8"
    )
    if catalogs:
        (root / "profiles").mkdir()
        for filename, profiles in catalogs.items():
            (root / "profiles" / filename).write_text(
                json.dumps({"name": f"{root.name}_{filename}", "profiles": profiles}), encoding="utf-8"
            )
    if files:
        (root / "code").mkdir()
        for filename, text in files.items():
            (root / "code" / filename).write_text(text, encoding="utf-8")
    return root


class PackCodeCheckTests(unittest.TestCase):
    def test_real_pack_passes_with_every_id_probed(self):
        result = check_pack_code(pack_root=REPO_ROOT / "skill_packs/libero90_legacy", repo_root=REPO_ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(len(result["files"]), 4)
        self.assertEqual(result["warnings"], [])
        for item in result["files"]:
            self.assertEqual(item["declared_ids"], item["checked_ids"])
        self.assertGreaterEqual(sum(len(item["declared_ids"]) for item in result["files"]), 40)

    def test_non_deterministic_sampler_is_rejected(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = _write_pack(Path(td) / "pack", {"grasp_profiles.py": NON_DETERMINISTIC})
            report = check_pack_code_file(root / "code" / "grasp_profiles.py", pack_root=root)
            self.assertFalse(report.ok)
            self.assertTrue(any("not deterministic" in item for item in report.errors), report.errors)

    def test_forbidden_import_and_call_are_rejected(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = _write_pack(Path(td) / "pack", {"geometry_profiles.py": FORBIDDEN_IMPORT})
            report = check_pack_code_file(root / "code" / "geometry_profiles.py", pack_root=root)
            self.assertFalse(report.ok)
            self.assertTrue(any("forbidden import" in item for item in report.errors), report.errors)

    def test_code_id_without_catalog_entry_is_rejected(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = _write_pack(
                Path(td) / "pack",
                {"geometry_profiles.py": CATALOG_MISMATCH},
                catalogs={"geometry.yaml": {"in_catalog": {"params": {}}}},
            )
            report = check_pack_code_file(root / "code" / "geometry_profiles.py", pack_root=root)
            self.assertFalse(report.ok)
            self.assertTrue(
                any("not_in_catalog" in item and "missing from profiles/geometry.yaml" in item for item in report.errors),
                report.errors,
            )
            self.assertEqual(report.checked_ids, ["in_catalog"])

    def test_unfilled_scaffold_is_only_a_warning(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = _write_pack(Path(td) / "pack", {"geometry_profiles.py": SCAFFOLD})
            report = check_pack_code_file(root / "code" / "geometry_profiles.py", pack_root=root)
            self.assertTrue(report.ok)
            self.assertTrue(any("scaffold" in item for item in report.warnings), report.warnings)

    def test_admission_check_selects_only_pack_code_channels(self):
        pack_root = REPO_ROOT / "skill_packs/libero90_legacy"
        rel = "skill_packs/libero90_legacy/code/geometry_profiles.py"
        selected = _pack_code_check_files(
            pack_root,
            [rel, "skill_packs/libero90_legacy/code/helpers.py", "docs/readme.md"],
            REPO_ROOT,
        )
        self.assertEqual(selected, [rel])

        config = CodeAdmissionConfig(
            repo_root=REPO_ROOT,
            out_dir=pack_root / "_unused",
            manifest_path=None,
            skill_files=[],
            index_path=pack_root / "skills" / "_index.yaml",
            pack_root=pack_root,
            base_ref="HEAD",
        )
        clean = run_pack_code_admission_check(config=config, changed_files=[rel], repo=REPO_ROOT)
        self.assertTrue(clean["ok"], clean["errors"])
        self.assertTrue(clean["files"])
        self.assertEqual(
            run_pack_code_admission_check(config=config, changed_files=["docs/readme.md"], repo=REPO_ROOT),
            {"ok": True, "files": [], "errors": [], "warnings": []},
        )

    def test_broken_pack_code_fails_code_admission(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td) / "pack"
            _write_pack(root, {"geometry_profiles.py": FORBIDDEN_IMPORT})
            rel_file = f"{root.relative_to(root.parent).as_posix()}/code/geometry_profiles.py"
            manifest = root / "code_patch_manifest.yaml"
            manifest.write_text(
                "\n".join(
                    [
                        "schema_version: 1",
                        "change_type:",
                        "  - geometry_hint",
                        "skill_ids:",
                        "  - fixture_skill",
                        "touched_files:",
                        f"  - {rel_file}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = run_code_admission(
                CodeAdmissionConfig(
                    repo_root=root.parent,
                    out_dir=root / "out",
                    manifest_path=manifest,
                    skill_files=[],
                    index_path=root / "skills" / "_index.yaml",
                    pack_root=root,
                    base_ref="HEAD",
                    changed_files=[rel_file],
                )
            )
            self.assertFalse(result["ok"])
            self.assertTrue(any("forbidden import" in item for item in result["errors"]), result["errors"])
            self.assertTrue((result.get("pack_code_check") or {}).get("files"))
            markdown = Path(result["result_markdown"]).read_text(encoding="utf-8")
            self.assertIn("## Pack Code Check", markdown)


if __name__ == "__main__":
    unittest.main()
