"""Runtime hook bus. One match per emit; highest priority wins."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .matcher import Match, match_skills
from .schema import ALLOWED_HOOKS, SkillSpec


class HookBus:
    def __init__(self, skills: Iterable[SkillSpec] | None = None, *, predicate_registry: Any = None) -> None:
        self.skills = [skill for skill in (skills or []) if skill.kind != "diagnostics"]
        self.predicate_registry = predicate_registry

    def emit(self, hook: str, state: Mapping[str, Any]) -> Match | None:
        if hook not in ALLOWED_HOOKS:
            raise ValueError(f"unknown hook: {hook}")
        return match_skills(self.skills, hook, state, predicate_registry=self.predicate_registry)
