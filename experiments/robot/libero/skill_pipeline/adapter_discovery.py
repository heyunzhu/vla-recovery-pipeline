"""Discover pack-local code adapters by conventional filename.

A pack may declare its adapter explicitly in ``pack.yaml`` or
``skills/_index.yaml``.  When it does not, the adapter is picked up from
``<pack>/code/<filename>`` as long as the file declares a non-empty id set
(``PROFILE_IDS`` / ``PREDICATE_IDS`` / ...).  Empty scaffold files are ignored
with a warning, so a template that was never filled in cannot break a run while
a half-written adapter still fails loudly at load time.

This keeps pack extension wiring uniform: dropping the adapter in the right file
is enough, and no silent "file exists but was never loaded" state remains.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

DEFAULT_PACK_CODE_DIRNAME = "code"

# ``PROFILE_IDS = (...)`` / ``PREDICATE_IDS: frozenset[str] = frozenset({...})``
_ID_ASSIGNMENT_TEMPLATE = r"^{name}\s*(?::[^=\n]+)?=\s*(?P<value>.+)$"
_EMPTY_LITERALS = frozenset({"()", "[]", "{}", "set()", "frozenset()", "frozenset([])", "none", '""', "''"})


def declares_ids(text: str, names: Iterable[str]) -> bool:
    """True when ``text`` assigns a non-empty literal to any of ``names``."""
    for name in names:
        pattern = re.compile(_ID_ASSIGNMENT_TEMPLATE.format(name=re.escape(str(name))), re.MULTILINE)
        for match in pattern.finditer(text):
            value = str(match.group("value") or "").strip().lower()
            if value and value not in _EMPTY_LITERALS:
                return True
    return False


def infer_pack_code_adapter_path(
    index_path: str | Path | None,
    filename: str,
    *,
    ids: Iterable[str] = ("PROFILE_IDS",),
    code_dirname: str = DEFAULT_PACK_CODE_DIRNAME,
) -> Path | None:
    """Return ``<pack>/code/<filename>`` when it exists and declares ``ids``."""
    if index_path in (None, ""):
        return None
    index = Path(index_path)
    candidate = index.parent.parent / code_dirname / filename
    if not candidate.exists():
        return None
    try:
        text = candidate.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - unreadable adapter is reported, not fatal
        logger.warning("pack adapter could not be read, ignoring: %s (%s)", candidate, exc)
        return None
    if not declares_ids(text, ids):
        logger.warning(
            "pack adapter declares no non-empty %s, ignoring: %s",
            "/".join(str(item) for item in ids),
            candidate,
        )
        return None
    return candidate
