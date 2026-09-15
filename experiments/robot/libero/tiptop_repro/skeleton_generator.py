from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .affordances import is_probably_articulated, is_probably_movable, is_probably_surface, object_affordances
from .cutamp_like import PlanSkeleton
from .predicates import SymbolicState
from .scene_graph import SceneGraph
from .scene_reader import SceneState
from .tamp_scene import GroundedAtom
from .task_parser import ParsedTask, language_requests_inside, language_requests_on_top, prefer_cabinet_body_name
from .task_semantics import TaskSemanticsResult

ALLOWED_SYMBOLIC_OPS = {"retreat", "pick", "place_on", "place_in", "open", "close", "move_aside"}


@dataclass(frozen=True)
class SymbolicPlanStep:
    op: str
    obj: Optional[str] = None
    target: Optional[str] = None
    relation: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {"op": self.op, "obj": self.obj, "target": self.target, "relation": self.relation}


@dataclass
class CandidateSkeleton:
    name: str
    steps: List[SymbolicPlanStep]
    reason: str
    source: str = "rule"
    score_hint: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def goal_atoms(self) -> List[GroundedAtom]:
        atoms: List[GroundedAtom] = []
        final_holding: Optional[str] = None
        for step in self.steps:
            if step.op == "pick" and step.obj:
                final_holding = step.obj
            elif step.op in {"place_on", "place_in"} and step.obj and step.target:
                atoms.append(GroundedAtom("on", (step.obj, step.target)))
                final_holding = None
        if final_holding:
            atoms.append(GroundedAtom("holding", (final_holding,)))
        atoms.append(GroundedAtom("handempty", ()))
        return atoms

    def executable_steps(self) -> List[str]:
        out: List[str] = []
        for step in self.steps:
            if step.op == "retreat":
                out.append("retreat_open")
            elif step.op == "move_aside":
                out.extend([
                    "move_above_obstacle",
                    "descend_to_obstacle",
                    "close_gripper",
                    "lift_obstacle",
                    "move_obstacle_aside",
                    "open_gripper",
                    "retreat_open",
                ])
            elif step.op == "pick":
                out.extend(["move_above_object", "descend_to_grasp", "close_gripper", "lift"])
            elif step.op in {"place_on", "place_in"}:
                out.extend(["move_above_goal", "slow_place"])
            elif step.op in {"open", "close"}:
                continue
        if not out:
            out = ["retreat_open"]
        if out[-1] != "retreat_open":
            out.append("retreat_open")
        return out

    def to_plan_skeleton(self) -> PlanSkeleton:
        return PlanSkeleton(name=self.name, steps=self.executable_steps(), reason=self.reason)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "reason": self.reason,
            "source": self.source,
            "score_hint": self.score_hint,
            "steps": [step.to_dict() for step in self.steps],
            "executable_steps": self.executable_steps(),
            "goal_atoms": [atom.to_dict() for atom in self.goal_atoms()],
            "warnings": list(self.warnings),
        }


@dataclass
class SkeletonGenerationResult:
    target: Optional[str]
    goal_objects: List[str]
    candidates: List[CandidateSkeleton]
    prompt: str = ""
    raw_response: str = ""
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    @property
    def goal_atoms(self) -> List[GroundedAtom]:
        if not self.candidates:
            return []
        return self.candidates[0].goal_atoms()

    def executable_skeletons(self) -> List[PlanSkeleton]:
        return [candidate.to_plan_skeleton() for candidate in self.candidates]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "goal_objects": list(self.goal_objects),
            "prompt": self.prompt,
            "raw_response": self.raw_response,
            "diagnostics": dict(self.diagnostics),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def build_skeleton_prompt(task: ParsedTask, graph: SceneGraph, task_semantics: TaskSemanticsResult | None = None) -> str:
    objects = [
        {
            "name": node.name,
            "role": node.role,
            "affordances": node.affordances,
            "dist_to_ee": round(float(node.dist_to_ee), 4),
            "geometry": {
                "kind": node.geometry.get("kind"),
                "half_extents": node.geometry.get("half_extents"),
                "mesh_path": node.geometry.get("mesh_path"),
            },
        }
        for node in graph.objects
    ]
    return (
        "You are a robot task-and-motion planning skeleton generator. "
        "Given a task and a scene graph, return JSON only. "
        "Allowed ops are retreat, pick, place_on, place_in, open, close, move_aside. "
        "Each candidate must include name, reason, and steps. "
        "Each step has op, obj, target, relation. "
        f"Task: {task.language}\n"
        f"Scene objects: {objects}\n"
        f"Table geometry: {graph.table_geometry}\n"
        f"World atoms: {graph.world_atoms}\n"
        f"Task atoms: {task_semantics.task_atoms if task_semantics is not None else graph.task_atoms}\n"
        f"Task progress: {task_semantics.task_progress if task_semantics is not None else graph.task_progress}\n"
        "Prefer short recovery skeletons that minimally disturb the scene and hand control back to the VLA."
    )


def _name_contains(name: str, tokens: Iterable[str]) -> bool:
    low = name.lower().replace("_", " ")
    return any(tok in low for tok in tokens)


def _choose_name_by_tokens(names: Sequence[str], tokens: Iterable[str], avoid: Optional[str] = None) -> Optional[str]:
    token_list = list(tokens)
    for name in names:
        if avoid is not None and name == avoid:
            continue
        if _name_contains(name, token_list):
            return name
    return None


def _choose_goal_name_by_tokens(names: Sequence[str], tokens: Iterable[str], avoid: Optional[str] = None) -> Optional[str]:
    token_list = list(tokens)
    for name in names:
        if avoid is not None and name == avoid:
            continue
        aff = object_affordances(name)
        if ("door_link" in aff or "fixture" in aff) and "door" not in token_list:
            continue
        if _name_contains(name, token_list):
            return name
    return None


def _find_goal_from_language(task: ParsedTask, object_names: Sequence[str], target: Optional[str]) -> Optional[str]:
    low = task.language.lower().replace("_", " ")
    if language_requests_on_top(task.language) and "cabinet" in low:
        cabinet_body = prefer_cabinet_body_name(object_names, avoid=target)
        if cabinet_body is not None:
            return cabinet_body
    if task.goal_hint and task.goal_hint in object_names and task.goal_hint != target:
        return task.goal_hint
    priority = [
        ("microwave", ("microwave",)),
        ("drawer", ("drawer",)),
        ("cabinet", ("cabinet",)),
        ("basket", ("basket",)),
        ("box", ("box",)),
        ("plate", ("plate",)),
        ("stove", ("stove",)),
        ("table", ("table",)),
    ]
    for key, tokens in priority:
        if key in low:
            if key == "cabinet" and not language_requests_inside(task.language):
                found = prefer_cabinet_body_name(object_names, avoid=target)
            else:
                found = _choose_goal_name_by_tokens(object_names, tokens, avoid=target)
            if found is not None:
                return found
    for name in object_names:
        if name != target and is_probably_surface(name):
            return name
    return None


def _find_door_for_goal(goal: Optional[str], object_names: Sequence[str]) -> Optional[str]:
    if goal is None:
        return None
    low_goal = goal.lower()
    if "microwave" in low_goal:
        return _choose_name_by_tokens(object_names, ("microdoorroot", "doorroot", "door"), avoid=goal)
    if "drawer" in low_goal or "cabinet" in low_goal:
        return _choose_name_by_tokens(object_names, ("door", "drawer"), avoid=goal)
    return None


def _verify_candidate(candidate: CandidateSkeleton, object_names: Sequence[str]) -> CandidateSkeleton:
    names = set(object_names)
    warnings: List[str] = list(candidate.warnings)
    verified_steps: List[SymbolicPlanStep] = []
    for step in candidate.steps:
        if step.op not in ALLOWED_SYMBOLIC_OPS:
            warnings.append(f"drop_unsupported_op:{step.op}")
            continue
        if step.obj is not None and step.obj not in names:
            warnings.append(f"missing_obj:{step.obj}")
            continue
        if step.target is not None and step.target not in names:
            warnings.append(f"missing_target:{step.target}")
            continue
        if step.op == "pick" and step.obj is not None and not is_probably_movable(step.obj):
            warnings.append(f"pick_non_movable:{step.obj}")
        if step.op in {"open", "close"} and step.obj is not None and not is_probably_articulated(step.obj):
            warnings.append(f"articulation_unknown:{step.obj}")
        verified_steps.append(step)
    return CandidateSkeleton(
        name=candidate.name,
        steps=verified_steps,
        reason=candidate.reason,
        source=candidate.source,
        score_hint=candidate.score_hint,
        warnings=warnings,
    )


class RuleSkeletonGenerator:
    """LLM-style skeleton generator with a deterministic backend."""

    def generate(
        self,
        task: ParsedTask,
        scene: SceneState,
        graph: SceneGraph,
        sym: SymbolicState,
        task_semantics: TaskSemanticsResult | None = None,
    ) -> SkeletonGenerationResult:
        object_names = [node.name for node in graph.objects]
        target = task_semantics.target_object if task_semantics is not None else None
        if target is None:
            target = sym.target.name if sym.target is not None else task.target_hint
        if target not in object_names:
            target = _choose_name_by_tokens(object_names, ("mug", "bowl", "plate", "book", "object", "can", "bottle"))
        goal = task_semantics.goal_object if task_semantics is not None else _find_goal_from_language(task, object_names, target)
        door = _find_door_for_goal(goal, object_names)
        progress = task_semantics.task_progress if task_semantics is not None else {}
        low = task.language.lower().replace("_", " ")
        wants_inside = bool(progress.get("requires_inside", False)) or language_requests_inside(low)
        wants_close = bool(progress.get("requires_closed", False)) or "close" in low or "closed" in low
        wants_open = "open" in low or (goal is not None and ("microwave" in goal.lower() or "drawer" in goal.lower()))
        candidates: List[CandidateSkeleton] = []
        candidates.append(CandidateSkeleton(
            name="retreat_only_low_disturbance",
            steps=[SymbolicPlanStep("retreat")],
            reason="first_move_to_low_risk_pose_then_return_to_vla",
            score_hint=0.25,
        ))

        if target is not None and goal is not None:
            placement_op = "place_in" if wants_inside or ("microwave" in goal.lower() or "drawer" in goal.lower()) else "place_on"
            semantic_steps: List[SymbolicPlanStep] = [SymbolicPlanStep("retreat")]
            if wants_open and door is not None:
                semantic_steps.append(SymbolicPlanStep("open", obj=door, target=goal))
            semantic_steps.extend([
                SymbolicPlanStep("pick", obj=target),
                SymbolicPlanStep(placement_op, obj=target, target=goal),
            ])
            if wants_close and door is not None:
                semantic_steps.append(SymbolicPlanStep("close", obj=door, target=goal))
            candidates.append(CandidateSkeleton(
                name=f"semantic_{placement_op}_minimal",
                steps=semantic_steps,
                reason="semantic_task_skeleton_minimal_disturbance",
                score_hint=0.0,
            ))
            candidates.append(CandidateSkeleton(
                name=f"semantic_{placement_op}_wide_retreat",
                steps=[SymbolicPlanStep("retreat"), SymbolicPlanStep("retreat"), *semantic_steps[1:]],
                reason="semantic_task_skeleton_extra_clearance",
                score_hint=0.1,
            ))

        if target is not None:
            candidates.append(CandidateSkeleton(
                name="recover_regrasp_only",
                steps=[SymbolicPlanStep("retreat"), SymbolicPlanStep("pick", obj=target)],
                reason="recover_object_control_then_return_to_vla",
                score_hint=0.2,
            ))

        if sym.nearest is not None and target is not None and sym.nearest.name != target:
            candidates.insert(0, CandidateSkeleton(
                name="clear_nearest_then_semantic_recover",
                steps=[
                    SymbolicPlanStep("retreat"),
                    SymbolicPlanStep("move_aside", obj=sym.nearest.name),
                    SymbolicPlanStep("pick", obj=target),
                ] + ([SymbolicPlanStep("place_in" if wants_inside else "place_on", obj=target, target=goal)] if goal else []),
                reason="nearest_object_blocks_target",
                score_hint=0.05,
            ))

        verified = [_verify_candidate(candidate, object_names) for candidate in candidates]
        verified = [candidate for candidate in verified if candidate.steps]
        verified.sort(key=lambda item: (item.score_hint, len(item.executable_steps())))
        goal_objects = [name for name in [goal, door] if name is not None]
        diagnostics = {
            "backend": "rule",
            "num_scene_objects": len(object_names),
            "object_affordances": {node.name: object_affordances(node.name) for node in graph.objects},
            "uses_task_semantics": task_semantics is not None,
            "task_progress": dict(progress),
            "required_final_atoms": task_semantics.required_final_atoms if task_semantics is not None else [],
            "approximates_place_in_as_on": any(step.op == "place_in" for candidate in verified for step in candidate.steps),
            "articulated_ops_symbolic_only": any(step.op in {"open", "close"} for candidate in verified for step in candidate.steps),
        }
        return SkeletonGenerationResult(
            target=target,
            goal_objects=goal_objects,
            candidates=verified,
            prompt=build_skeleton_prompt(task, graph, task_semantics),
            diagnostics=diagnostics,
        )
