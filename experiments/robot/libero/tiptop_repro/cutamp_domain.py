from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

from .affordances import (
    is_probably_articulated,
    is_probably_movable,
    is_probably_surface,
    is_top_support_surface,
    object_affordances,
)
from .scene_reader import SceneState


@dataclass(frozen=True)
class ActionSchema:
    name: str
    parameters: List[str]
    preconditions: List[str]
    effects: List[str]
    continuous_parameters: List[str]
    supported_by_executor: bool
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "parameters": list(self.parameters),
            "preconditions": list(self.preconditions),
            "effects": list(self.effects),
            "continuous_parameters": list(self.continuous_parameters),
            "supported_by_executor": bool(self.supported_by_executor),
            "diagnostics": dict(self.diagnostics),
        }


def build_action_schemas(scene: SceneState, surface_names: Iterable[str] = ()) -> List[ActionSchema]:
    names = list(scene.objects.keys())
    surfaces = sorted({name for name in names if is_probably_surface(name)} | set(surface_names) | {"table"})
    movables = sorted([name for name in names if is_probably_movable(name)])
    articulated = sorted([name for name in names if is_probably_articulated(name)])
    schemas: List[ActionSchema] = []
    for obj in movables:
        schemas.append(
            ActionSchema(
                name="pick",
                parameters=[obj],
                preconditions=["handempty(gripper)", f"movable({obj})"],
                effects=[f"holding(gripper,{obj})"],
                continuous_parameters=[f"grasp_candidate({obj})"],
                supported_by_executor=True,
            )
        )
        for surface in surfaces:
            if surface == obj:
                continue
            pred = "place_in" if "container" in object_affordances(surface) and not is_top_support_surface(surface) else "place_on"
            effect = "inside" if pred == "place_in" else "on"
            pre = [f"holding(gripper,{obj})"]
            if pred == "place_in":
                pre.append(f"open({surface})")
            schemas.append(
                ActionSchema(
                    name=pred,
                    parameters=[obj, surface],
                    preconditions=pre,
                    effects=[f"{effect}({obj},{surface})", "handempty(gripper)"],
                    continuous_parameters=[f"place_candidate({surface})"],
                    supported_by_executor=(pred == "place_on"),
                    diagnostics={"executor_gap": "place_in primitive not implemented"} if pred == "place_in" else {},
                )
            )
    for obj in articulated:
        schemas.append(
            ActionSchema(
                name="open",
                parameters=[obj],
                preconditions=[f"closed({obj})"],
                effects=[f"open({obj})"],
                continuous_parameters=[f"articulation_pose({obj})"],
                supported_by_executor=False,
                diagnostics={"executor_gap": "open articulated primitive not implemented"},
            )
        )
        schemas.append(
            ActionSchema(
                name="close",
                parameters=[obj],
                preconditions=[f"open({obj})"],
                effects=[f"closed({obj})"],
                continuous_parameters=[f"articulation_pose({obj})"],
                supported_by_executor=False,
                diagnostics={"executor_gap": "close articulated primitive not implemented"},
            )
        )
    schemas.append(
        ActionSchema(
            name="retreat",
            parameters=[],
            preconditions=[],
            effects=["safe_pose(gripper)"],
            continuous_parameters=["retreat_pose"],
            supported_by_executor=True,
        )
    )
    schemas.append(
        ActionSchema(
            name="open_gripper_for_recovery",
            parameters=[],
            preconditions=["gripper_closed(gripper)"],
            effects=["handempty(gripper)", "not_holding(gripper)"],
            continuous_parameters=[],
            supported_by_executor=True,
            diagnostics={
                "recovery_operator": True,
                "native_cutamp_gap": "represented for recovery planning metadata; native cuTAMP still optimizes pick/place/move skeletons",
            },
        )
    )
    schemas.append(
        ActionSchema(
            name="retreat_to_safe_pose",
            parameters=[],
            preconditions=["can_retreat(gripper,retreat_pose)"],
            effects=["safe_pose(gripper)", "not_stuck_like(gripper)"],
            continuous_parameters=["retreat_pose"],
            supported_by_executor=True,
            diagnostics={"recovery_operator": True},
        )
    )
    for obj in movables:
        schemas.append(
            ActionSchema(
                name="move_to_pregrasp",
                parameters=[obj],
                preconditions=[f"handempty(gripper)", f"recoverable({obj})"],
                effects=[f"near_gripper({obj})"],
                continuous_parameters=[f"pregrasp_pose({obj})"],
                supported_by_executor=True,
                diagnostics={
                    "recovery_operator": True,
                    "native_cutamp_gap": "pregrasp is represented as grasp-candidate initialization in the native cuTAMP call",
                },
            )
        )
    return schemas
