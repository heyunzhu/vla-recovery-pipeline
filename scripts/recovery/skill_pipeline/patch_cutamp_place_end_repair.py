"""Give cuTAMP's Place:end stage the same repair path Pick:end already has.

Why
---
The per-stage cuRobo trace shows every particle dying in the same place:

    Pick:pick_approach      ok
    Pick:end                IK_FAIL -> repaired by patch_cutamp_end_pose_repair
    Place:retract           ok
    Place:place_approach    ok          (the arm gets above the drawer)
    Place:end               IK_FAIL      <- 40/40, and nothing retries

The Place branch gives `place_approach` four attempts (5/10/15/20 cm above the target)
but `Place:end` exactly one, with no fallback at all - not even the
`INVALID_PARTIAL_POSE_COST_METRIC` retry that Pick:end has.

Measured separately with verify_place_ik.py: at the placement pose IK solves 0/64 even
with an *empty* world, so this is reachability, not collision. Raising the pose helps
with a sharp threshold - 0/64 at +0 cm, 1/64 at +2 cm, 11/64 at +5 cm - which is why a
small back-off is the right repair and why it composes with the release-offset fix.

What it changes
---------------
One guarded block in `particle_initialization.py`'s sibling file `motion_solver.py`, at
the Place `end` call site:

  1. retry the same pose unconstrained (drops the partial-pose metric), mirroring Pick;
  2. then walk the shared `_grasp_pose_repairs` list (180 deg about the approach axis,
     then increasing depth back-offs).

Not gated by an env var: it only ever runs after the unmodified code would have raised
MotionPlanningError, so it cannot change behaviour except by turning a failure into a
success. Repair attempts are traced as `end_pose_repair` events like Pick's are.

Requires patch_cutamp_end_pose_repair.py to have run first (it defines
`_grasp_pose_repairs`).

Usage
-----
    python scripts/recovery/skill_pipeline/patch_cutamp_place_end_repair.py
    python scripts/recovery/skill_pipeline/patch_cutamp_place_end_repair.py --revert
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sys
import time
from typing import Optional

DEFAULT_TARGET = pathlib.Path(
    os.environ.get("ROOT", "/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo")
) / "third_party" / "cuTAMP" / "cutamp" / "motion_solver.py"

PREREQUISITE = "_grasp_pose_repairs"

ANCHOR = (
    '                end_result = traced_plan_single(f"{ground_op.name}:end", approach_js, '
    "Pose.from_matrix(world_from_ee), constrained_plan_config)\n"
    "                if not end_result.success:\n"
    "                    raise MotionPlanningError(\n"
)

INSERT = '''                if not end_result.success:
                    end_result = traced_plan_single(
                        f"{ground_op.name}:end_unconstrained_fallback",
                        approach_js,
                        Pose.from_matrix(world_from_ee),
                        plan_config,
                    )
                if not end_result.success:
                    for repair_label, repair_matrix in _grasp_pose_repairs(world_from_ee):
                        repair_result = traced_plan_single(
                            f"{ground_op.name}:place_end_{repair_label}",
                            approach_js,
                            Pose.from_matrix(repair_matrix),
                            plan_config,
                        )
                        _trace_motion_event(
                            {
                                "event": "end_pose_repair",
                                "timeline": timeline,
                                "stage": f"{ground_op.name}:end",
                                "repair": repair_label,
                                "success": bool(repair_result.success),
                                "status": str(repair_result.status),
                                "original_status": str(end_result.status),
                            }
                        )
                        if repair_result.success:
                            end_result = repair_result
                            break
'''

MARKER = "place_end_"
EDITS = (("place end repair loop", ANCHOR, INSERT + ANCHOR),)


def latest_backup(target: pathlib.Path) -> Optional[pathlib.Path]:
    backups = sorted(target.parent.glob(f"{target.name}.bak_*"))
    return backups[-1] if backups else None


def apply(target: pathlib.Path) -> int:
    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"already patched: {target}")
        return 0
    if PREREQUISITE not in text:
        print(f"refusing: {target} lacks {PREREQUISITE}; run patch_cutamp_end_pose_repair.py first")
        return 3
    for label, old, _ in EDITS:
        count = text.count(old)
        if count != 1:
            print(f"FAIL {label}: expected exactly 1 match, found {count}; nothing written")
            return 1
    backup = target.with_suffix(f"{target.suffix}.bak_{int(time.time())}")
    shutil.copy2(target, backup)
    print(f"backup: {backup}")
    for label, old, new in EDITS:
        text = text.replace(old, new, 1)
        print(f"ok   {label}")
    target.write_text(text, encoding="utf-8")
    print(f"patched: {target}")
    return 0


def revert(target: pathlib.Path) -> int:
    backup = latest_backup(target)
    if backup is None:
        print(f"no backup next to {target}")
        return 1
    shutil.copy2(backup, target)
    print(f"restored {target} from {backup}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default=str(DEFAULT_TARGET))
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args(argv)
    target = pathlib.Path(args.target).expanduser()
    if not target.exists():
        print(f"not found: {target}")
        return 2
    return revert(target) if args.revert else apply(target)


if __name__ == "__main__":
    sys.exit(main())
