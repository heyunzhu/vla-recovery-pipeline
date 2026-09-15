"""Map a matched skill to an existing execution-bridge backend. Never env.step 7-D here."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping

from .matcher import Match
from .schema import SkillSchemaError, SkillSpec

RESERVED_RUNNER_BACKENDS = frozenset({"cutamp_recover"})


@dataclass
class BackendDecision:
    skip: bool = False
    keep_gripper_closed: bool = False
    gripper_hold_value: float | None = None
    enter_recovery: bool = False
    skill_id: str = ""
    backend: str = ""
    recovery_hints: dict[str, Any] = field(default_factory=dict)
    hint_sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


BackendFn = Callable[..., BackendDecision]


def _keep_gripper_closed(state: Mapping[str, Any], skill: SkillSpec | None = None) -> BackendDecision:
    from .backends.keep_closed import keep_gripper_closed

    return keep_gripper_closed(state, skill=skill)


def _cutamp_recover(state: Mapping[str, Any], skill: SkillSpec | None = None) -> BackendDecision:
    del state
    return BackendDecision(
        enter_recovery=True,
        skill_id=skill.id if skill is not None else "cutamp_recover",
        backend="cutamp_recover",
        recovery_hints=dict(skill.recovery_hints or {}) if skill is not None else {},
    )


BACKENDS: dict[str, BackendFn] = {
    "keep_gripper_closed": _keep_gripper_closed,
    "cutamp_recover": _cutamp_recover,
}


def _unique(items: list[Any]) -> list[Any]:
    out: list[Any] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _merge_value(old: Any, new: Any, conflicts: list[dict[str, Any]], path: str) -> Any:
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        merged = dict(old)
        for key, value in new.items():
            child = f"{path}.{key}" if path else str(key)
            merged[key] = _merge_value(merged.get(key), value, conflicts, child) if key in merged else value
        return merged
    if isinstance(old, list) and isinstance(new, list):
        return _unique(list(new) + list(old))
    if old is None or old == "":
        return new
    if new is None or new == "":
        return old
    if old != new:
        conflicts.append({"path": path, "old": old, "new": new})
    return new


def merge_recovery_hints(sources: list[tuple[str, int, Mapping[str, Any]]]) -> dict[str, Any]:
    """Merge main-skill hints with matching recovery_hint policies.

    Sources must be ordered from lowest to highest precedence. Later scalar
    values override earlier scalar values; lists are unioned with newer entries
    first so higher-priority policy preferences lead search order.
    """
    merged: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for skill_id, priority, hints in sources:
        hints = dict(hints or {})
        if not hints:
            continue
        provenance.append({"skill_id": skill_id, "priority": int(priority)})
        merged = _merge_value(merged, hints, conflicts, "")
    if provenance or conflicts:
        params = dict(merged.get("params") or {})
        if provenance:
            params["hint_sources"] = provenance
        if conflicts:
            params["hint_conflicts"] = conflicts
        merged["params"] = params
    return merged


def available_backends() -> list[str]:
    return sorted(BACKENDS)


def dispatch(match: Match, state: Mapping[str, Any]) -> BackendDecision:
    name = str(match.skill.backend)
    fn = BACKENDS.get(name)
    if fn is None:
        raise SkillSchemaError(f"unknown backend: {name}")
    decision = fn(state, skill=match.skill)
    decision.skill_id = decision.skill_id or match.skill.id
    decision.backend = decision.backend or name
    if not decision.recovery_hints and match.skill.recovery_hints:
        decision.recovery_hints = dict(match.skill.recovery_hints)
    return decision
