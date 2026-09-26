"""Patch cuTAMP's 4-DOF placement to respect the object's actual resting frame.

Why
---
`place_4dof_sampler` samples (x, y, z, yaw) and the caller builds the object pose with
`action_4dof_to_mat4x4`, which is yaw about world z on top of an **identity** orientation.
That silently assumes the object's local z is the axis pointing up when it rests.

Objects registered from a MuJoCo box geom do not satisfy that: the cream cheese reaches
cuTAMP as the geom's own frame, where the thin axis is local **x** (dims
[0.0179, 0.0427, 0.0812]). So the sampler places it 90 deg wrong - standing on its end -
and, because the grasp is defined relative to the object frame, the derived hand pose ends
up with the tool axis horizontal instead of pointing down. Measured on the task04 place
problem: `IK success: 0/64`, reproduced offline as 0/128 with hand z_col = (-0.956, -0.292, 0)
instead of (0, 0, -1).

The second symptom comes from the same assumption: the "drop the object onto the surface"
correction (`obj_z_delta`) reads the object spheres' local z, so it computes the height of
a standing object (about 5 cm) instead of a lying one (about 1 cm).

What it changes
---------------
One guarded block in `particle_initialization.py`'s Place branch, active only when
`CUTAMP_PLACE_REST_FRAME=1`:

  * the placement rotation becomes `Rz(yaw) @ R_rest`, i.e. the object's own resting
    orientation spun by the sampled yaw, instead of `Rz(yaw)` alone;
  * the placement z is recomputed from the object's spheres **in its resting frame**, so
    its lowest point lands on the surface top.

It touches nothing else: the object's registered frame, the grasps and the pick path are
all left alone, which is why this is the safe place to test the diagnosis before deciding
where the fix lives permanently.

Usage
-----
    python scripts/recovery/skill_pipeline/patch_cutamp_place_rest_frame.py
    python scripts/recovery/skill_pipeline/patch_cutamp_place_rest_frame.py --revert
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
) / "third_party" / "cuTAMP" / "cutamp" / "particle_initialization.py"

IMPORT_OLD = "import logging\nfrom typing import Optional\n"
IMPORT_NEW = "import logging\nimport os\nfrom typing import Optional\n"

ANCHOR = (
    "                # Select the placements that are not in collision with the object\n"
    "                world_from_obj = action_4dof_to_mat4x4(sampled_placements)  # desired placement pose\n"
)

INSERT = '''                if os.environ.get("CUTAMP_PLACE_REST_FRAME", "") == "1":
                    # The 4-DOF sample carries yaw only, on top of an identity orientation.
                    # Rebuild it as "the object's real resting orientation, spun by that yaw",
                    # and re-derive the drop so the lowest point meets the surface top.
                    from cutamp.utils.obb import get_object_obb

                    _rest = world.get_object_pose(obj)
                    _rest_rot = _rest[:3, :3]
                    world_from_obj = world_from_obj.clone()
                    world_from_obj[:, :3, :3] = world_from_obj[:, :3, :3] @ _rest_rot
                    _rest_spheres = transform_spheres(obj_spheres, _rest)
                    _delta = -(_rest_spheres[:, 2] - _rest_spheres[:, 3]).min()
                    _top = float(get_object_obb(world.get_object(surface), None).surface_z)
                    world_from_obj[:, 2, 3] = _top + _delta + 2e-3
                    log_debug(
                        f"{header}. REST_FRAME rest_drop={float(_delta):.4f} surface_top={_top:.4f} "
                        f"obj_z=[{float(world_from_obj[:, 2, 3].min()):.4f}, {float(world_from_obj[:, 2, 3].max()):.4f}]"
                    )

'''

MARKER = "CUTAMP_PLACE_REST_FRAME"
EDITS = (("import os", IMPORT_OLD, IMPORT_NEW), ("rest-frame block", ANCHOR, ANCHOR + INSERT))


def latest_backup(target: pathlib.Path) -> Optional[pathlib.Path]:
    backups = sorted(target.parent.glob(f"{target.name}.bak_*"))
    return backups[-1] if backups else None


def apply(target: pathlib.Path) -> int:
    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"already patched: {target}")
        return 0
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
