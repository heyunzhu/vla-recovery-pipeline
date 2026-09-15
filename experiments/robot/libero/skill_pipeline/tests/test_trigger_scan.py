from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.predicate_registry import load_predicate_registry
from experiments.robot.libero.skill_pipeline.schema import spec_from_mapping
from experiments.robot.libero.skill_pipeline.trigger_scan import (
    ScanConfig,
    scan_roots,
    write_scan_outputs,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _repair_skill():
    return spec_from_mapping(
        {
            "id": "target_bowl_preclose",
            "kind": "repair",
            "hook": "after_pi0_query",
            "priority": 50,
            "backend": "cutamp_recover",
            "applies_to": {"all": [{"target_name_matches": "bowl"}]},
            "trigger": {
                "all": [
                    {"aperture_gt": 0.025},
                    {"holding_status_is": "handempty_or_unconfirmed"},
                    {"target_ee_distance_lt": 0.11},
                ]
            },
        }
    )


def _grasp_hint():
    return spec_from_mapping(
        {
            "id": "bowl_grasp_hint",
            "kind": "recovery_hint",
            "track": "pair",
            "scope": "grasp",
            "priority": 10,
            "applies_to": {"all": [{"target_name_matches": "bowl"}]},
            "recovery_hints": {"grasp_profile": "bowl_rim_diagonal_mixed_topdown_v1"},
        }
    )


class TriggerScanTests(unittest.TestCase):
    def test_scan_replays_current_matcher_over_query_trace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run = root / "run"
            ep0 = run / "lane_tasks01_gpu0_deadbee" / "task01" / "ep00"
            ep1 = run / "lane_tasks01_gpu0_deadbee" / "task01" / "ep01"
            ep0.mkdir(parents=True)
            ep1.mkdir(parents=True)
            (ep0 / "episode.json").write_text(
                json.dumps({"success": False, "task_id_1based": 1, "episode_idx": 0, "seed": 90}),
                encoding="utf-8",
            )
            (ep1 / "episode.json").write_text(
                json.dumps({"success": True, "task_id_1based": 1, "episode_idx": 1, "seed": 91}),
                encoding="utf-8",
            )
            _write_jsonl(
                ep0 / "query_trace.jsonl",
                [
                    {
                        "query_idx": 0,
                        "target_name": "akita_black_bowl_1_main",
                        "aperture": 0.04,
                        "holding_status": "handempty_or_unconfirmed",
                        "target_ee_distance_m": 0.30,
                    },
                    {
                        "query_idx": 1,
                        "target_name": "akita_black_bowl_1_main",
                        "aperture": 0.04,
                        "holding_status": "handempty_or_unconfirmed",
                        "target_ee_distance_m": 0.08,
                    },
                ],
            )
            _write_jsonl(
                ep1 / "query_trace.jsonl",
                [
                    {
                        "query_idx": 0,
                        "target_name": "akita_black_bowl_1_main",
                        "aperture": 0.04,
                        "holding_status": "confirmed_holding",
                        "target_ee_distance_m": 0.05,
                    }
                ],
            )

            report = scan_roots([run], [_repair_skill(), _grasp_hint()])
            by_episode = {(row["task"], row["episode"]): row for row in report["episodes"]}
            ep0_report = by_episode[("task01", "ep00")]
            ep1_report = by_episode[("task01", "ep01")]

            self.assertEqual(report["overall"]["episodes"], 2)
            self.assertEqual(ep0_report["first_repair_query_idx"], 1)
            self.assertEqual(ep0_report["first_repair_skill"], "target_bowl_preclose")
            self.assertIsNone(ep1_report["first_repair_query_idx"])
            self.assertEqual(ep1_report["hint_episode_hits"], ["bowl_grasp_hint"])

            by_skill = {row["skill_id"]: row for row in report["skills"]}
            self.assertEqual(by_skill["target_bowl_preclose"]["episode_matches"], 1)
            self.assertEqual(by_skill["target_bowl_preclose"]["winner_episodes"], 1)
            self.assertEqual(by_skill["bowl_grasp_hint"]["episode_matches"], 2)
            self.assertEqual(by_skill["bowl_grasp_hint"]["success_episode_matches"], 1)
            self.assertEqual(by_skill["bowl_grasp_hint"]["failed_episode_matches"], 1)

    def test_scan_can_write_machine_and_human_readable_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run = root / "run"
            ep = run / "lane_tasks01_gpu0_deadbee" / "task01" / "ep00"
            ep.mkdir(parents=True)
            (ep / "episode.json").write_text(json.dumps({"success": False}), encoding="utf-8")
            _write_jsonl(
                ep / "query_trace.jsonl",
                [
                    {
                        "query_idx": 3,
                        "target_name": "akita_black_bowl_1_main",
                        "aperture": 0.04,
                        "holding_status": "handempty_or_unconfirmed",
                        "target_ee_distance_m": 0.08,
                    }
                ],
            )
            report = scan_roots([run], [_repair_skill()], ScanConfig(include_hints=False))
            outputs = write_scan_outputs(report, root / "out")

            for path in outputs.values():
                self.assertTrue(Path(path).exists(), path)
            markdown = Path(outputs["markdown"]).read_text(encoding="utf-8")
            self.assertIn("Offline Skill Trigger Scan", markdown)
            self.assertIn("target_bowl_preclose", markdown)

    def test_scan_recomputes_pack_diagnostics_for_custom_predicate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "pack"
            provider = pack / "code" / "diagnostics" / "wrong_intent.py"
            provider.parent.mkdir(parents=True)
            provider.write_text(
                "def compute(state, history):\n"
                "    return {'diag_wrong_intent': state.get('intent_object_name') != state.get('target_name')}\n",
                encoding="utf-8",
            )
            diagnostics = pack / "diagnostics" / "registry.yaml"
            diagnostics.parent.mkdir(parents=True)
            diagnostics.write_text(
                "signals:\n"
                "  - id: wrong_intent_shadow\n"
                "    status: shadow\n"
                "    hook: after_pi0_query\n"
                "    provider: ../code/diagnostics/wrong_intent.py\n"
                "    description: test-only wrong intent signal\n"
                "    online_safe: false\n"
                "    uses_future_rollout: false\n"
                "    uses_oracle_success: false\n"
                "    inputs: [target_name, intent_object_name]\n"
                "    outputs: [diag_wrong_intent]\n",
                encoding="utf-8",
            )
            predicates = pack / "profiles" / "predicates.yaml"
            predicates.parent.mkdir(parents=True)
            predicates.write_text(
                "name: test_predicates\n"
                "predicates:\n"
                "  trigger:\n"
                "    wrong_intent_diag:\n"
                "      source: diagnostic_signal\n"
                "      signal: diag_wrong_intent\n"
                "      op: is\n"
                "      evidence_role: failure_evidence\n",
                encoding="utf-8",
            )
            predicate_registry = load_predicate_registry(predicates)
            skill = spec_from_mapping(
                {
                    "id": "wrong_intent_repair",
                    "kind": "repair",
                    "hook": "after_pi0_query",
                    "priority": 40,
                    "backend": "cutamp_recover",
                    "applies_to": {"all": [{"target_name_matches": "bowl"}]},
                    "trigger": {"all": [{"wrong_intent_diag": True}]},
                },
                predicate_registry=predicate_registry,
            )
            ep = root / "run" / "task09" / "ep00"
            ep.mkdir(parents=True)
            (ep / "episode.json").write_text(json.dumps({"success": False}), encoding="utf-8")
            _write_jsonl(
                ep / "query_trace.jsonl",
                [
                    {
                        "query_idx": 6,
                        "target_name": "akita_black_bowl_1_main",
                        "intent_object_name": "plate_1_main",
                    }
                ],
            )

            report = scan_roots(
                [root / "run"],
                [skill],
                ScanConfig(
                    include_hints=False,
                    diagnostic_signal_registry=diagnostics,
                    diagnostic_signal_statuses="shadow",
                ),
                predicate_registry=predicate_registry,
            )

            self.assertEqual(report["episodes"][0]["first_repair_skill"], "wrong_intent_repair")
            self.assertTrue(
                report["query_matches"][0]["diagnostic_signals"]["values"]["diag_wrong_intent"]
            )

    def test_scan_accepts_generated_task_directories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ep = root / "run" / "libero_90_gen_t022_pick_place_on_surface_deadbeef" / "ep00"
            ep.mkdir(parents=True)
            (ep / "episode.json").write_text(
                json.dumps(
                    {
                        "generated_task_id": "libero_90_gen_t022_pick_place_on_surface_deadbeef",
                        "success": False,
                        "task_description": "put the black bowl on the plate",
                    }
                ),
                encoding="utf-8",
            )
            _write_jsonl(
                ep / "query_trace.jsonl",
                [
                    {
                        "query_idx": 1,
                        "target_name": "akita_black_bowl_1_main",
                        "aperture": 0.04,
                        "holding_status": "handempty_or_unconfirmed",
                        "target_ee_distance_m": 0.08,
                    }
                ],
            )

            report = scan_roots([root / "run"], [_repair_skill()])

            self.assertEqual(report["overall"]["episodes"], 1)
            self.assertEqual(
                report["episodes"][0]["task"],
                "libero_90_gen_t022_pick_place_on_surface_deadbeef",
            )


if __name__ == "__main__":
    unittest.main()
