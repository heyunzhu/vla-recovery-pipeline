"""Small helpers for wiring resolved skill-pack config into CLI entrypoints."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .skill_pack import ResolvedSkillConfig


def diagnostic_signal_statuses_for_cli(
    skill_config: ResolvedSkillConfig,
    requested: str | None = None,
    *,
    explicit_registry: bool = False,
) -> str:
    """Choose diagnostic statuses for offline CLI gates.

    Online runs only compute diagnostic signals when the caller asks for active
    statuses.  Offline gates need one extra default: when a skill pack provides
    its own registry, scan shadow/online signals so pack predicates can replay.
    """

    if requested and str(requested).strip():
        return str(requested).strip()
    pack_has_registry = (
        skill_config.skill_pack is not None
        and skill_config.skill_pack.diagnostic_signal_registry is not None
    )
    if explicit_registry or pack_has_registry:
        return "shadow,online" if skill_config.diagnostic_signal_registry else ""
    return ""


def diagnostic_provider_roots_for_cli(
    skill_config: ResolvedSkillConfig,
    extra_roots: Sequence[str | Path] | None = None,
) -> tuple[Path, ...]:
    roots: list[Path] = [Path(root) for root in (extra_roots or ()) if str(root)]
    if skill_config.skill_pack is not None:
        roots.append(skill_config.skill_pack.root)
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return tuple(unique)
