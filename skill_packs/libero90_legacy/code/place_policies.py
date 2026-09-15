"""LIBERO-90 place policy adapter.

The core executor only knows generic hover / align / release controls. This
adapter owns the benchmark-specific choice of which controls a place profile
should enable.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping


ADAPTER_NAME = "libero90_legacy_place_policies"
PROFILE_IDS = (
    "task38_held_transfer_keep_z_v1",
    "caddy_book_compartment_align_budget_v1",
)


def _hook(profile_data: Mapping[str, Any], name: str) -> dict[str, Any]:
    hooks = profile_data.get("hooks") or {}
    if not isinstance(hooks, Mapping):
        return {}
    value = hooks.get(name) or {}
    if not isinstance(value, Mapping):
        return {}
    return copy.deepcopy(dict(value))


def resolve_hover_policy(
    profile: str,
    profile_data: Mapping[str, Any],
    params: Mapping[str, Any],
) -> dict[str, Any]:
    del profile, params
    return _hook(profile_data, "hover")


def resolve_align_policy(
    profile: str,
    profile_data: Mapping[str, Any],
    params: Mapping[str, Any],
) -> dict[str, Any]:
    del profile, params
    return _hook(profile_data, "align")


def resolve_release_policy(
    profile: str,
    profile_data: Mapping[str, Any],
    params: Mapping[str, Any],
) -> dict[str, Any]:
    del profile, params
    return _hook(profile_data, "release")
