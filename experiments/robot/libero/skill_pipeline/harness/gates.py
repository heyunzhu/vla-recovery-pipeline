from __future__ import annotations

from typing import Any


def evaluate_gates(summary: dict[str, Any], gates: dict[str, Any] | None = None) -> dict[str, Any]:
    gates = gates or {}
    failures: list[str] = []
    warnings: list[str] = []
    overall = summary.get("overall") or {}
    overall_rate = float(overall.get("success_rate") or 0.0)
    min_overall = gates.get("min_overall_success_rate")
    if min_overall is not None and overall_rate < float(min_overall):
        failures.append(f"overall success_rate {overall_rate:.3f} < required {float(min_overall):.3f}")

    per_task_min = gates.get("per_task_min_success_rate")
    if per_task_min is not None:
        threshold = float(per_task_min)
        for row in summary.get("tasks") or []:
            rate = float(row.get("success_rate") or 0.0)
            if rate < threshold:
                failures.append(f"{row.get('task')} success_rate {rate:.3f} < required {threshold:.3f}")

    max_recovery_rate = gates.get("max_recovery_episode_rate")
    if max_recovery_rate is not None:
        episodes = int(overall.get("episodes") or 0)
        recovery_calls = int(overall.get("recovery_calls") or 0)
        rate = recovery_calls / episodes if episodes else 0.0
        if rate > float(max_recovery_rate):
            warnings.append(f"recovery_calls/episodes {rate:.3f} > warning threshold {float(max_recovery_rate):.3f}")

    return {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "warnings": warnings,
        "gates": gates,
    }
