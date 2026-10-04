"""Offline SAM proposals with historical labels, deliberately not VisualDetection."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class HistoricalBoxProposal:
    mask: np.ndarray
    category: str  # Historical category hypothesis, not current classification.
    seed_detection_index: int
    category_verified: bool = False
    identity_verified: bool = False
    planning_allowed: bool = False
    execution_allowed: bool = False

    def __post_init__(self):
        if self.category_verified or self.identity_verified or self.planning_allowed or self.execution_allowed:
            raise ValueError('historical box proposals cannot verify categories, identity or authorize execution')
        mask = np.asarray(self.mask)
        if mask.ndim != 2 or mask.dtype != np.bool_ or not mask.any():
            raise ValueError('proposal requires a nonempty 2D bool mask')
        if not self.category or self.seed_detection_index < 0:
            raise ValueError('proposal requires historical category and seed index')


def mask_box(mask):
    mask = np.asarray(mask)
    if mask.ndim != 2 or mask.dtype != np.bool_ or not mask.any():
        raise ValueError('seed requires a nonempty 2D bool mask')
    y, x = np.nonzero(mask)
    return [int(x.min()), int(y.min()), int(x.max()) + 1, int(y.max()) + 1]
