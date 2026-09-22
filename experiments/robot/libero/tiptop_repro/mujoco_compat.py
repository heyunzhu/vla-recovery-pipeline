"""Small compatibility helpers for mujoco-py and modern mujoco bindings.

The project can receive either a robosuite/mujoco-py model wrapper (which
exposes ``*_names`` and ``*_name2id`` helpers) or a modern ``mujoco.MjModel``
(which exposes only indexed arrays plus ``mj_id2name``/``mj_name2id``).
Keeping this difference in one module prevents articulation discovery from
silently returning an empty scene on the modern binding.

Every caller indexes the returned list by the RAW MuJoCo object id
(``model.jnt_type[jid]``, ``model.geom_bodyid[gid]``, ...), so the list must be
index-aligned with those ids and have exactly ``njnt``/``ngeom``/``nbody``/
``nsite`` entries.  robosuite's ``*_names`` tuple does NOT always satisfy that:
for the libero_90 KITCHEN_SCENE models it lists only the NAMED objects, so with
182 geoms of which 4 are unnamed it returns 178 entries and every name after the
first unnamed geom is shifted onto the wrong id.  Trusting it caused two
distinct failures on unmodified code:

* ``read_articulation_structure`` raises ``IndexError`` while scanning
  ``range(ngeom)`` -> ``read_scene`` swallows it -> ``articulation_structure``
  is empty -> the TAMP problem cannot be built at all;
* where no id exceeds the shortened list the binding is built from the WRONG
  geometry with no error at all (``white_cabinet_1_g18`` resolved to a side
  panel ~0.15 m away from the real handle).

The ``*_names`` attribute is therefore only trusted when its length matches the
model count; otherwise names are rebuilt per id through ``*_id2name`` /
``mj_id2name``, which are id-addressed and immune to the shift.
"""
from __future__ import annotations

from typing import Any, List, Optional


_KIND_INFO = {
    "joint": ("njnt", "mjOBJ_JOINT"),
    "body": ("nbody", "mjOBJ_BODY"),
    "geom": ("ngeom", "mjOBJ_GEOM"),
    "site": ("nsite", "mjOBJ_SITE"),
}


def _count(model: Any, kind: str) -> Optional[int]:
    try:
        return int(getattr(model, _KIND_INFO[kind][0]))
    except Exception:
        return None


def _indexed_names(model: Any, kind: str, count: Optional[int]) -> Optional[List[str]]:
    """Names looked up per object id, or ``None`` when the binding cannot do it."""
    if count is None:
        return None
    getter = getattr(model, f"{kind}_id2name", None)
    if callable(getter):
        values, named = [], 0
        for idx in range(count):
            try:
                value = getter(idx)
            except Exception:
                values = None
                break
            if value:
                named += 1
            values.append("" if value is None else str(value))
        if values is not None and (named or count == 0):
            return values
    try:
        import mujoco

        obj_type = getattr(mujoco.mjtObj, _KIND_INFO[kind][1])
        return [mujoco.mj_id2name(model, obj_type, idx) or "" for idx in range(count)]
    except Exception:
        return None


def _attr_names(model: Any, kind: str) -> Optional[List[str]]:
    attr = getattr(model, f"{kind}_names", None)
    if attr is None:
        return None
    try:
        return ["" if value is None else str(value) for value in list(attr)]
    except Exception:
        return None


def model_names(model: Any, kind: str) -> List[str]:
    """Return stable indexed names for a model, including unnamed entries."""
    if model is None or kind not in _KIND_INFO:
        return []
    count = _count(model, kind)
    table = _attr_names(model, kind)
    if table is not None and (count is None or len(table) == count):
        return table
    indexed = _indexed_names(model, kind, count)
    if indexed is not None:
        return indexed
    return table if table is not None else []


def model_name_to_id(model: Any, kind: str, name: str) -> Optional[int]:
    """Resolve a named model object for both supported MuJoCo bindings."""
    if model is None or not name or kind not in _KIND_INFO:
        return None
    target = str(name)
    count = _count(model, kind)
    index: Optional[int] = None
    method = getattr(model, f"{kind}_name2id", None)
    if callable(method):
        try:
            index = int(method(target))
        except Exception:
            index = None
    if index is None:
        try:
            import mujoco

            obj_type = getattr(mujoco.mjtObj, _KIND_INFO[kind][1])
            resolved = int(mujoco.mj_name2id(model, obj_type, target))
            index = resolved if resolved >= 0 else None
        except Exception:
            index = None
    # Verify against an id-addressed table, which a shortened name tuple cannot corrupt.
    indexed = _indexed_names(model, kind, count) if index is not None else None
    if indexed is not None and 0 <= index < len(indexed):
        if indexed[index] == target:
            return index
        return indexed.index(target) if target in indexed else None
    if index is not None:
        return index
    table = model_names(model, kind)
    try:
        return table.index(target)
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
