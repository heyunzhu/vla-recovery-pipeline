"""Lightweight recovery diagnostics with no planner or GPU dependencies."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

LOGGER = logging.getLogger(__name__)


def append_recovery_diagnostic(event: Dict[str, Any]) -> None:
    """Append one JSONL diagnostic when ``CUTAMP_RECOVERY_DIAG_JSONL`` is set."""
    raw_path = str(os.environ.get("CUTAMP_RECOVERY_DIAG_JSONL", "") or "").strip()
    if not raw_path:
        return
    try:
        target = Path(raw_path)
        if target.parent != Path(""):
            target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:  # pragma: no cover - diagnostics must never break recovery
        LOGGER.warning("could not append recovery diagnostics to %s: %s", raw_path, exc)


def recovery_attempt_summary(attempt: Any, **extra: Any) -> Dict[str, Any]:
    """Return the compact planning and execution fields worth retaining."""
    backend = getattr(attempt, "planner_backend", None) or {}
    real = backend.get("real_cutamp") or {}
    return {
        "attempt_idx": getattr(attempt, "attempt_idx", None),
        "plan_reason": getattr(attempt, "plan_reason", ""),
        "execution_source": backend.get("execution_source", ""),
        "feasible": getattr(attempt, "feasible", None),
        "selected_recovery_goal": (backend.get("execution_bridge_diagnostics") or {}).get(
            "selected_recovery_goal"
        ),
        "real_cutamp_feasible": real.get("feasible"),
        "real_cutamp_failure_reason": real.get("failure_reason"),
        "real_cutamp_plan_type": (real.get("diagnostics") or {}).get("plan_type"),
        **extra,
    }
