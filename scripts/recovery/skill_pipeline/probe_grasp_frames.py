"""Is GPT's `target_curobo` in the same EE frame our pipeline uses?

Decisive test: take their solved joint configurations (`solutions`), run OUR forward kinematics on
them, and compare with their `target_curobo` / `target_world`. If our FK reproduces their target the
frames agree and the imported grasp is fine; if the difference is a constant transform, that transform
is exactly what the import must compensate.

Also asks our own solver for those targets, so a solver-level mismatch is visible too.

Usage (py310 overlay):
    .../cutamp_runner_py310_overlay.sh scripts/recovery/skill_pipeline/probe_grasp_frames.py \
        --solve-json <problem.json> --contact-ik <contact_ik.json> --report-out <report.json>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.tiptop_repro.articulation import (  # noqa: E402
    ArticulatedPart,
    ArticulationError,
)
from experiments.robot.libero.tiptop_repro.collision_report import _load_problem  # noqa: E402


def pose_err(a: np.ndarray, b: np.ndarray):
    pos = float(np.linalg.norm(a[:3, 3] - b[:3, 3]))
    r = a[:3, :3].T @ b[:3, :3]
    ang = float(np.arccos(np.clip((np.trace(r) - 1.0) / 2.0, -1.0, 1.0)))
    return pos, ang


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--contact-ik", required=True)
    parser.add_argument("--candidates", default="0,1,8")
    parser.add_argument("--report-out", default="")
    args = parser.parse_args()

    cfg, problem = _load_problem(pathlib.Path(args.solve_json))
    binding = problem.articulation_options["bindings"][0]
    part = ArticulatedPart(**problem.articulations[binding["part_id"]])
    handle_pose = part.handle_pose(part.reference_position)
    q_init = np.asarray(problem.q_init, dtype=float)

    from experiments.robot.libero.tiptop_repro.articulation_curobo import CuroboArticulationMotion
    motion = CuroboArticulationMotion(problem, part, cfg.robot)

    contact = json.loads(pathlib.Path(args.contact_ik).read_text())
    want = {int(v) for v in args.candidates.split(",") if v.strip()}
    print("native_from_curobo_hand (their file):")
    print(np.round(np.asarray(contact.get("native_from_curobo_hand"), dtype=float), 6))
    print()

    out = {"solve_json": args.solve_json, "contact_ik": args.contact_ik, "rows": []}
    for row in contact["rows"]:
        cid = row["candidate_id"]
        if cid not in want:
            continue
        target_c = np.asarray(row["target_curobo"], dtype=float)
        target_w = np.asarray(row["target_world"], dtype=float)
        print(f"===== candidate {cid}: their target_curobo xyz = {np.round(target_c[:3, 3], 4).tolist()}")
        rec = {"candidate_id": cid, "their_target_curobo_xyz": np.round(target_c[:3, 3], 4).tolist(),
               "their_target_world_xyz": np.round(target_w[:3, 3], 4).tolist(), "fk_rows": []}
        for i, q in enumerate(row.get("solutions", [])[:4]):
            q = np.asarray(q, dtype=float)
            fk = motion.fk(q)
            pos_c, rot_c = pose_err(fk, target_c)
            pos_w, rot_w = pose_err(fk, target_w)
            transform = target_c @ np.linalg.inv(fk)
            rec["fk_rows"].append({
                "solution_index": i,
                "fk_xyz": np.round(fk[:3, 3], 4).tolist(),
                "err_vs_target_curobo_m": round(pos_c, 5),
                "err_vs_target_curobo_rad": round(rot_c, 5),
                "err_vs_target_world_m": round(pos_w, 5),
                "err_vs_target_world_rad": round(rot_w, 5),
                "target_curobo_from_fk_translation": np.round(transform[:3, 3], 4).tolist(),
            })
            print(f"  sol{i}: our FK xyz={np.round(fk[:3, 3], 4).tolist()}  "
                  f"|FK-their_curobo|={pos_c:.5f} m {rot_c:.5f} rad   "
                  f"|FK-their_world|={pos_w:.5f} m {rot_w:.5f} rad")
        # can OUR solver reach their target at all?
        try:
            rec["our_ik_on_their_target"] = motion.ik(target_c, q_init) is not None
        except Exception as exc:  # noqa: BLE001
            rec["our_ik_on_their_target"] = f"error:{type(exc).__name__}:{exc}"
        pre = target_c.copy()
        pre[:3, 3] -= target_c[:3, 2] * 0.05
        try:
            points = motion._plan(q_init, pre, part.reference_position)
            rec["our_plan_single_to_pre"] = {"ok": True, "points": int(len(points))}
        except ArticulationError as exc:
            rec["our_plan_single_to_pre"] = {"ok": False, "error": str(exc)}
        print(f"  our IK on their target: {rec['our_ik_on_their_target']}")
        print(f"  our plan_single to their pre-grasp: {rec['our_plan_single_to_pre']}")
        out["rows"].append(rec)
        print()

    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))
    if args.report_out:
        pathlib.Path(args.report_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
