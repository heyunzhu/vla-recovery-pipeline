"""Patch cuTAMP's Pick:end fallback so an IK-infeasible sampled grasp can be repaired.

Why this exists
---------------
Recovery's `Pick` operator plans a two-stage motion: `pick_approach` (5 cm short of
the object) and `end` (the grasp itself). The sampler's grasp pose is emitted once and
is never repaired, so when cuRobo answers `MotionGenStatus.IK_FAIL` for `end` the whole
plan dies even though nearby, grasp-equivalent poses are reachable.

Measured on the LIBERO-Goal task04 recovery problem for
`holding(cream_cheese_1_main)`, start state cleared with the start-state retreat, with
`CUTAMP_MOTION_TRACE_JSONL` on:

  * `pick_approach` (no pose metric)                        -> success
  * `end` (constrained partial-pose config)                 -> IK_FAIL
  * `end` with the partial-pose metric cleared              -> IK_FAIL  (not the metric)
  * `end` rotated 180 deg about the approach axis, same depth -> IK_FAIL
  * `end` at the same orientation, 5 mm shallower           -> success

The last one is the repair this patch reaches for: same orientation, same approach
axis, tool tip moved 5 mm up. The object is 17.9 mm thick, so the tool tip stays inside
it and the jaws still straddle it - this is not "grasping air". With the repair the
problem returns `feasible=True` and a 4-step executable plan.

What it changes
---------------
Three edits to `cutamp/motion_solver.py`, all inside `solve_curobo`:

  1. `import math`
  2. a `_grasp_pose_repairs()` helper
  3. an end-pose repair loop after the existing partial-pose fallback

Repair order is cheapest-and-most-equivalent first: 180 deg about the approach axis
(a parallel jaw cannot tell that grasp apart), then the unrotated pose at increasing
depth back-offs. Rotating by 90/270 deg changes which object axis the jaws close
across, so those only run behind `CUTAMP_END_REPAIR_ALLOW_NON_EQUIVALENT_YAW=1`.

The patch is idempotent and takes a timestamped backup before writing.

Usage
-----
    python scripts/recovery/skill_pipeline/patch_cutamp_end_pose_repair.py
    python scripts/recovery/skill_pipeline/patch_cutamp_end_pose_repair.py --motion-solver /path/to/motion_solver.py
    python scripts/recovery/skill_pipeline/patch_cutamp_end_pose_repair.py --revert

Environment knobs read by the patched code at plan time:

    CUTAMP_END_REPAIR_DEPTHS_M                  default "0.005,0.010"
    CUTAMP_END_REPAIR_ALLOW_NON_EQUIVALENT_YAW   default "0" (off)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sys
import time
from typing import Optional

DEFAULT_MOTION_SOLVER = pathlib.Path(
    os.environ.get("ROOT", "/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo")
) / "third_party" / "cuTAMP" / "cutamp" / "motion_solver.py"

IMPORTS_OLD = "import json\nimport logging\nimport os\n"
IMPORTS_NEW = "import json\nimport logging\nimport math\nimport os\n"

HELPER_ANCHOR = "    # Iterate through skeleton and motion plan\n"

HELPER_NEW = '''    def _grasp_pose_repairs(base_matrix):
        """Grasp-equivalent alternatives to a sampled end pose that has no IK.

        A parallel jaw cannot tell a grasp from the same grasp rotated 180 deg about
        its approach axis, so that variant is always tried first. Shallower depths
        come next, cheapest first. Rotating by 90/270 deg changes which object axis
        the jaws close across, so it stays behind an explicit opt-in.
        """
        import math as _math

        def rot_z(angle):
            c, s = _math.cos(angle), _math.sin(angle)
            return torch.tensor(
                [[c, -s, 0.0, 0.0], [s, c, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
                device=base_matrix.device,
                dtype=base_matrix.dtype,
            )

        depths = []
        for text in os.environ.get("CUTAMP_END_REPAIR_DEPTHS_M", "0.005,0.010").split(","):
            text = text.strip()
            if text:
                try:
                    depths.append(float(text))
                except ValueError:
                    pass
        candidates = [(_math.pi, 0.0)]
        for dz in sorted(depths):
            candidates.append((0.0, dz))
            candidates.append((_math.pi, dz))
        if os.environ.get("CUTAMP_END_REPAIR_ALLOW_NON_EQUIVALENT_YAW", "0") == "1":
            candidates.append((_math.pi / 2.0, 0.0))
            candidates.append((1.5 * _math.pi, 0.0))
        repairs = []
        for yaw, dz in candidates:
            matrix = base_matrix @ rot_z(yaw)
            if dz:
                matrix = matrix.clone()
                matrix[2, 3] = matrix[2, 3] + dz
            repairs.append((f"yaw{int(round(_math.degrees(yaw))) % 360}_dz{dz:+.3f}", matrix))
        return repairs

'''

FALLBACK_OLD = (
    '                if not end_result.success and _is_invalid_partial_pose_cost_metric(end_result):\n'
    '                    _trace_motion_event({"event": "partial_pose_fallback", "timeline": timeline, '
    '"stage": f"{ground_op.name}:end", "status": str(end_result.status)})\n'
    '                    end_result = traced_plan_single(f"{ground_op.name}:end_unconstrained_fallback", '
    'approach_js, Pose.from_matrix(world_from_ee), plan_config)\n'
)

FALLBACK_NEW = FALLBACK_OLD + '''                if not end_result.success:
                    for repair_label, repair_matrix in _grasp_pose_repairs(world_from_ee):
                        repair_result = traced_plan_single(
                            f"{ground_op.name}:end_{repair_label}",
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

MARKER = "_grasp_pose_repairs"


def latest_backup(target: pathlib.Path) -> Optional[pathlib.Path]:
    backups = sorted(target.parent.glob(f"{target.name}.bak_*"))
    return backups[-1] if backups else None


EDITS = (
    ("imports", IMPORTS_OLD, IMPORTS_NEW),
    ("helper", HELPER_ANCHOR, HELPER_NEW + HELPER_ANCHOR),
    ("fallback", FALLBACK_OLD, FALLBACK_NEW),
)


def apply(target: pathlib.Path) -> int:
    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"already patched: {target}")
        return 0
    # Validate every anchor before touching anything, so a mismatch against a
    # different cuTAMP revision cannot leave a half-patched file behind.
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
    parser.add_argument("--motion-solver", default=str(DEFAULT_MOTION_SOLVER))
    parser.add_argument("--revert", action="store_true", help="Restore the newest backup instead.")
    args = parser.parse_args(argv)
    target = pathlib.Path(args.motion_solver).expanduser()
    if not target.exists():
        print(f"not found: {target}")
        return 2
    return revert(target) if args.revert else apply(target)


if __name__ == "__main__":
    sys.exit(main())
