"""Capability accounting: where each round's capabilities came from.

``new_code`` means the round added a capability id in pack code, ``borrowed``
means it reused one a pack already provided, ``default`` means it only named
engine-provided profiles, ``skill_only`` means it named no capability at all, and
``unknown`` means the audit could not be recomputed.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.robot.libero.skill_pipeline.mine import (
    _mine_summary_payload,
    admitted_capability_used,
    classify_capability_source,
    engine_capability_ids,
    ingest_mine_draft,
    load_mine_state,
    step_mine,
    write_mine_summary,
)
from experiments.robot.libero.skill_pipeline.tests.test_mine import (
    _default_grasp_hint_md,
    _draft_md,
    _write_episode,
)


FIXTURE_SKILL = """---
id: grasp_fixture
name: Fixture grasp hint
kind: recovery_hint
track: fail_only
scope: grasp
priority: 50
when_to_apply: Fixture.
when_not_to_apply: Never.
failure_signature:
  - Fixture only.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "bowl"
recovery_hints:
  grasp_profile: can_body_lower_side_v1
evidence:
  tasks:
    - fixture
  episodes:
    - fixture
---

## Intent

Fixture skill.
"""

FIXTURE_CAPS = {
    "schema_version": 1,
    "name": "acct_caps",
    "mode": "strict",
    "capabilities": {
        "grasp_profiles": ["can_body_lower_side_v1"],
        "place_profiles": [],
        "repair_profiles": [],
        "grounding_profiles": [],
        "geometry_profiles": [],
        "geometry_hint_keys": [],
        "geometry_hint_intents": [],
        "grounding_hint_keys": [],
        "grounding_hint_intents": [],
        "executor_options": [],
        "place_candidate_policies": [],
        "place_yaw_policies": [],
        "release_modes": [],
    },
}


class CapabilityAccountingTests(unittest.TestCase):
    def test_classify_capability_source(self):
        self.assertEqual(
            classify_capability_source({"grasp_profiles": ["can_body_lower_side_v1"]}, {"grasp_profiles": ["new_v1"]}),
            "new_code",
        )
        self.assertEqual(classify_capability_source({"grasp_profiles": ["hollow_bowl_rim_topdown"]}, {}), "default")
        self.assertEqual(classify_capability_source({"grasp_profiles": ["libero_topdown"]}, {}), "default")
        self.assertEqual(classify_capability_source({"grasp_profiles": ["can_body_lower_side_v1"]}, {}), "borrowed")
        self.assertEqual(classify_capability_source({"executor_options": ["recovery_entry_lift_m"]}, {}), "borrowed")
        self.assertEqual(classify_capability_source({}, {}), "skill_only")
        self.assertEqual(classify_capability_source(None, {}), "unknown")

    def test_engine_capability_ids_cover_native_grasp_profiles(self):
        ids = engine_capability_ids()
        self.assertIn("hollow_bowl_rim_topdown", ids)
        self.assertIn("libero_topdown", ids)
        self.assertNotIn("can_body_lower_side_v1", ids)

    def test_admitted_capability_used_reads_the_registry_audit(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td) / "pack"
            (root / "skills" / "fail_only" / "recovery_hint" / "grasp").mkdir(parents=True)
            (root / "skills" / "_index.yaml").write_text(
                json.dumps({"name": "acct_pack", "capability_registry": "../capabilities.yaml", "online": [], "fail_only": []}),
                encoding="utf-8",
            )
            (root / "capabilities.yaml").write_text(json.dumps(FIXTURE_CAPS), encoding="utf-8")
            rel = "fail_only/recovery_hint/grasp/grasp_fixture.md"
            (root / "skills" / rel).write_text(FIXTURE_SKILL, encoding="utf-8")

            used = admitted_capability_used(root / "skills", [rel], capability_registry=root / "capabilities.yaml")
            self.assertEqual(used, {"grasp_profiles": ["can_body_lower_side_v1"]})
            self.assertEqual(classify_capability_source(used, {}), "borrowed")
            # A path that cannot be read means "unknown", not "no capability used".
            self.assertIsNone(
                admitted_capability_used(root / "skills", ["fail_only/missing.md"], capability_registry=root / "capabilities.yaml")
            )
            self.assertIsNone(admitted_capability_used(root / "skills", [], capability_registry=root / "capabilities.yaml"))

    def test_ingest_records_accounting_for_a_trigger_only_draft(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            skills = root / "skills"
            out = root / "mine"
            run = root / "run"
            (skills / "fail_only" / "trigger").mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            out.mkdir(parents=True, exist_ok=True)
            _write_episode(run / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            draft = root / "draft.md"
            draft.write_text(_draft_md(), encoding="utf-8")

            result = ingest_mine_draft(draft_md=draft, run_dir=run, skills_root=skills, out_dir=out, task_id=1)

            self.assertTrue(result["ok"], result)
            entry = load_mine_state(out / "mine_state.json")["tasks"]["1"]
            accounting = entry["last_capability_accounting"]
            self.assertEqual(accounting["capability_source"], "skill_only")
            self.assertEqual(accounting["added_capability_ids"], [])
            self.assertEqual(accounting["code_admission_ok"], None)
            self.assertEqual(accounting["used_capabilities"], {})

            summary = _mine_summary_payload(load_mine_state(out / "mine_state.json"))
            self.assertEqual(summary["capability_sources"], {"skill_only": 1})
            self.assertEqual(summary["tasks"][0]["capability_source"], "skill_only")

    def test_ingest_bundle_records_engine_default_grasp(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            run = root / "run"
            skills = root / "skills"
            out = root / "mine"
            bundle_root = root / "bundle"
            (bundle_root / "drafts" / "repair").mkdir(parents=True)
            (bundle_root / "drafts" / "grasp").mkdir(parents=True)
            skills.mkdir(parents=True)
            (skills / "_index.yaml").write_text(
                "capability_registry: ../capabilities.yaml\nonline: []\nfail_only: []\n",
                encoding="utf-8",
            )
            (root / "capabilities.yaml").write_text(
                "schema_version: 1\nname: test_caps\nmode: strict\ncapabilities:\n"
                "  grasp_profiles: []\n"
                "  place_profiles: []\n"
                "  geometry_hint_keys: []\n"
                "  geometry_hint_intents: []\n"
                "  grounding_hint_keys: []\n"
                "  grounding_hint_intents: []\n"
                "  executor_options: []\n"
                "  place_candidate_policies: []\n"
                "  place_yaw_policies: []\n"
                "  release_modes: []\n",
                encoding="utf-8",
            )
            _write_episode(run / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1])
            (bundle_root / "drafts" / "repair" / "open_hand_stall.md").write_text(_draft_md(), encoding="utf-8")
            (bundle_root / "drafts" / "grasp" / "grasp_default_cabinet_test.md").write_text(
                _default_grasp_hint_md(),
                encoding="utf-8",
            )
            (bundle_root / "bundle.yaml").write_text(
                "\n".join(
                    [
                        "bundle_id: cabinet_bundle_test",
                        "diagnosis:",
                        "  primary_failure_layer: grasp",
                        "drafts:",
                        "  - file: drafts/repair/open_hand_stall.md",
                        "    role: entrypoint",
                        "    category: repair",
                        "  - file: drafts/grasp/grasp_default_cabinet_test.md",
                        "    role: grasp_hint",
                        "    category: grasp",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = ingest_mine_draft(
                bundle_yaml=bundle_root / "bundle.yaml",
                run_dir=run,
                skills_root=skills,
                out_dir=out,
                task_id=1,
            )

            self.assertTrue(result["ok"], result)
            entry = load_mine_state(out / "mine_state.json")["tasks"]["1"]
            accounting = entry["last_capability_accounting"]
            self.assertEqual(accounting["used_capabilities"], {"grasp_profiles": ["default"]})
            self.assertEqual(accounting["capability_source"], "default")
            self.assertEqual(accounting["added_capability_ids"], [])

    def test_summary_markdown_lists_sources(self):
        state = {
            "completed": [],
            "awaiting_task": None,
            "awaiting_kind": None,
            "tasks": {
                "5": {
                    "status": "passed",
                    "writes": 1,
                    "last_triage": {"status": "covered", "primary_signature": "success_threshold_met"},
                    "last_capability_accounting": {
                        "used_capabilities": {"grasp_profiles": ["can_body_lower_side_v1"]},
                        "added_capability_ids": ["new_grasp_v1"],
                        "changed_files": ["skill_packs/p/code/grasp_profiles.py"],
                        "code_admission_ok": True,
                        "capability_source": "new_code",
                    },
                },
                "7": {"status": "awaiting_draft", "writes": 0},
            },
        }
        payload = _mine_summary_payload(state)
        self.assertEqual(payload["capability_sources"], {"new_code": 1})
        self.assertEqual(payload["tasks"][0]["added_capability_ids"], ["new_grasp_v1"])

        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            paths = write_mine_summary(td, state)
            md = Path(paths["summary_md"]).read_text(encoding="utf-8")
            self.assertIn("capability sources: {'new_code': 1}", md)
            self.assertIn("capability=new_code", md)
            self.assertIn("added capabilities: ['new_grasp_v1']", md)


if __name__ == "__main__":
    unittest.main()
