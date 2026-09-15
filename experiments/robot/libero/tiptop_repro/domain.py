from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class PlanStep:
    name: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryPlan:
    steps: List[PlanStep]
    reason: str

    def names(self) -> List[str]:
        return [step.name for step in self.steps]
