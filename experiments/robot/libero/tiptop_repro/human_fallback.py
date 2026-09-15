from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class HumanFallbackRequest:
    reason: str
    planner_context: Dict[str, Any]
    attempted_plans: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class HumanFallbackResult:
    requested: bool
    reason: str
    hint: str = ""


class HumanFallback:
    """Logging-only human fallback hook."""

    def request(self, request: HumanFallbackRequest) -> HumanFallbackResult:
        return HumanFallbackResult(requested=True, reason=request.reason)
