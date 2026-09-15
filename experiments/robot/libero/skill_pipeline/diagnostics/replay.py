"""Offline replay helpers for diagnostic signal providers."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .runtime import DiagnosticSignalRuntime


def state_from_query_row(row: Mapping[str, Any]) -> dict[str, Any]:
    state = dict(row)
    if "aperture" not in state and state.get("gripper_aperture") is not None:
        state["aperture"] = state.get("gripper_aperture")
    if "task_description" not in state and state.get("language") is not None:
        state["task_description"] = state.get("language")
    return state


def replay_query_rows(
    rows: Iterable[Mapping[str, Any]],
    runtime: DiagnosticSignalRuntime,
    *,
    hook: str = "after_pi0_query",
) -> list[dict[str, Any]]:
    augmented: list[dict[str, Any]] = []
    for row in rows:
        copied = dict(row)
        copied["diagnostic_signals"] = runtime.compute(hook, state_from_query_row(row))
        augmented.append(copied)
    return augmented
