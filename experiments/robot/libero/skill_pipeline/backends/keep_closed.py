"""Keep the gripper closed on a Pick/MoveFree trajectory after a confirmed lift-follow."""

from __future__ import annotations

from typing import Mapping

from ..dispatcher import BackendDecision
from ..schema import SkillSpec


def keep_gripper_closed(state: Mapping[str, Any], skill: SkillSpec | None = None) -> BackendDecision:
    close_value = state.get("gripper_close_value")
    if close_value is None:
        close_value = 1.0
    return BackendDecision(
        keep_gripper_closed=True,
        gripper_hold_value=float(close_value),
        skip=False,
        skill_id=skill.id if skill is not None else "keep_gripper_closed",
        backend="keep_gripper_closed",
    )
