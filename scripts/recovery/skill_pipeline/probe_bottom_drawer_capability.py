"""Preflight a configured bottom-drawer capability against a recorded problem.

This runs the real cuTAMP articulation solve without starting an episode.  It is intentionally
strict: the binding must address the recorded part exactly, and no result file is written unless
the requested config can be represented and attempted.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.tiptop_repro.articulation import ArticulatedPart, PathSettings  # noqa: E402
from experiments.robot.libero.tiptop_repro.collision_report import _load_problem  # noqa: E402
from experiments.robot.libero.tiptop_repro.cutamp_articulation import solve  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--budget-sec", type=float, default=90.0)
    args = parser.parse_args()

    solve_path = pathlib.Path(args.solve_json)
    try:
        backend_cfg, problem = _load_problem(solve_path)
    except TypeError as exc:
        # Recorded solve payloads can contain runner options removed by a later branch.
        # They do not affect the reconstructed scene, so retain only current dataclass fields.
        if "unexpected keyword argument" not in str(exc):
            raise
        from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
            RealCuTAMPBackendConfig, _problem_from_dict,
        )
        payload = json.loads(solve_path.read_text(encoding="utf-8"))
        allowed = {field.name for field in dataclasses.fields(RealCuTAMPBackendConfig)}
        backend_cfg = RealCuTAMPBackendConfig(**{
            key: value for key, value in payload.get("config", {}).items() if key in allowed
        })
        problem = _problem_from_dict(payload["problem"])
    options = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
    bindings = options.get("bindings", [])
    if len(bindings) != 1:
        raise ValueError("probe requires exactly one articulation binding")
    binding = bindings[0]
    part_id = binding["part_id"]
    if part_id not in problem.articulations:
        raise ValueError(f"recorded problem has no part {part_id}")
    values = dict(problem.articulations[part_id])
    for key in ("open_range", "closed_range", "target_source", "grasps", "grasp_profiles"):
        values[key] = binding.get(key, [] if key == "grasp_profiles" else values.get(key))
    part = ArticulatedPart(**values)
    problem.articulations = {part_id: part.to_dict()}
    problem.articulation_options = options

    from experiments.robot.libero.tiptop_repro.articulation_curobo import CuroboArticulationMotion

    motion = CuroboArticulationMotion(problem, part, backend_cfg.robot)
    plan = solve(
        part, binding.get("goal", "open"), problem.q_init, motion,
        PathSettings(**options.get("path_settings", {})), args.budget_sec,
    )
    report = {
        "solve_json": args.solve_json,
        "config": args.config,
        "part_id": part_id,
        "selected_grasp_index": plan.get("selected_grasp_index"),
        "selected_grasp_profile": plan.get("selected_grasp_profile"),
        "soft_contact_objects": list(motion.soft_contact_objects),
        "operators": [row["name"] for row in plan.get("operators", [])],
        "phases": [row["phase"] for row in plan.get("actions", [])],
        "action_point_counts": {
            row["phase"]: len(row.get("positions", [])) for row in plan.get("actions", [])
            if row.get("positions") is not None
        },
        "failed_candidates": plan.get("failed_candidates", []),
        "ok": True,
    }
    pathlib.Path(args.report_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
