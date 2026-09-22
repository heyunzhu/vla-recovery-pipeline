"""Small compatibility helpers for mujoco-py and modern mujoco bindings.

The project can receive either a robosuite/mujoco-py model wrapper (which
exposes ``*_names`` and ``*_name2id`` helpers) or a modern ``mujoco.MjModel``
(which exposes only indexed arrays plus ``mj_id2name``/``mj_name2id``).
Keeping this difference in one module prevents articulation discovery from
silently returning an empty scene on the modern binding.
"""
from __future__ import annotations

from typing import Any, List, Optional


_KIND_INFO = {
    "joint": ("njnt", "mjOBJ_JOINT"),
    "body": ("nbody", "mjOBJ_BODY"),
    "geom": ("ngeom", "mjOBJ_GEOM"),
    "site": ("nsite", "mjOBJ_SITE"),
}


def model_names(model: Any, kind: str) -> List[str]:
    """Return stable indexed names for a model, including unnamed entries."""
    if model is None or kind not in _KIND_INFO:
        return []
    attr = getattr(model, f"{kind}_names", None)
    if attr is not None:
        try:
            return ["" if value is None else str(value) for value in list(attr)]
        except Exception:
            pass
    count_attr, obj_name = _KIND_INFO[kind]
    try:
        count = int(getattr(model, count_attr))
    except Exception:
        return []
    try:
        import mujoco

        obj_type = getattr(mujoco.mjtObj, obj_name)
        return [mujoco.mj_id2name(model, obj_type, idx) or "" for idx in range(count)]
    except Exception:
        return []


def model_name_to_id(model: Any, kind: str, name: str) -> Optional[int]:
    """Resolve a named model object for both supported MuJoCo bindings."""
    if model is None or not name or kind not in _KIND_INFO:
        return None
    method = getattr(model, f"{kind}_name2id", None)
    if callable(method):
        try:
            return int(method(name))
        except Exception:
            pass
    try:
        import mujoco

        obj_type = getattr(mujoco.mjtObj, _KIND_INFO[kind][1])
        index = int(mujoco.mj_name2id(model, obj_type, str(name)))
        return index if index >= 0 else None
    except Exception:
        pass
    names = model_names(model, kind)
    try:
        return names.index(str(name))
    except ValueError:
        return None


def data_field(data: Any, legacy_name: str, modern_name: Optional[str] = None) -> Any:
    """Read a data array whose body pose spelling changed in modern mujoco."""
    if data is None:
        return None
    value = getattr(data, legacy_name, None)
    if value is not None:
        return value
    return getattr(data, modern_name or legacy_name, None)
