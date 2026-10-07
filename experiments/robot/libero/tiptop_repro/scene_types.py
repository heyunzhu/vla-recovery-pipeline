"""Shared scene data types; contains no simulator access or scene acquisition."""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Any,Dict,List,Optional
import numpy as np


@dataclass
class ObjectState:
    name: str
    pos: np.ndarray
    quat: Optional[np.ndarray] = None
    geometry: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JointState:
    name: str
    qpos: float
    qvel: float = 0.0


@dataclass
class SceneState:
    ee_pos: np.ndarray
    ee_quat: np.ndarray
    gripper_qpos: np.ndarray
    robot_qpos: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    objects: Dict[str, ObjectState] = field(default_factory=dict)
    joints: Dict[str, JointState] = field(default_factory=dict)
    robot_joint_debug: Dict[str, Any] = field(default_factory=dict)
    contacts: List[Dict[str, Any]] = field(default_factory=list)
    holding_evidence: Dict[str, Any] = field(default_factory=dict)
    raw_obs_keys: tuple[str, ...] = ()

    @property
    def gripper_open(self) -> bool:
        # Compatibility for oracle callers; visual consumers must not infer handempty.
        return float(np.mean(np.abs(self.gripper_qpos))) > 0.02

    def nearest_object(self) -> Optional[ObjectState]:
        if not self.objects:
            return None
        return min(self.objects.values(), key=lambda obj: float(np.linalg.norm(obj.pos - self.ee_pos)))
