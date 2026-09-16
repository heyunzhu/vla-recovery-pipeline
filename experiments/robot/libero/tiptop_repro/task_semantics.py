from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .affordances import is_probably_surface, object_affordances
from .llm_client import LLMClientConfig, OpenAIResponsesClient
from .scene_graph import Atom, SceneGraph, atom_key, make_atom
from .task_parser import ParsedTask, language_requests_inside, language_requests_on_top, prefer_cabinet_body_name


ALLOWED_TASK_PREDICATES = {
    "target",
    "goal",
    "goal_container",
    "goal_surface",
    "requires_final",
    "on",
    "inside",
    "open",
    "closed",
    "holding",
}


@dataclass
class TaskSemanticsResult:
    target_object: Optional[str]
    goal_object: Optional[str]
    relevant_objects: List[str]
    task_atoms: List[Atom]
    required_final_atoms: List[Atom]
    task_progress: Dict[str, Any]
    prompt: str = ""
    raw_response: str = ""
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_object": self.target_object,
            "goal_object": self.goal_object,
            "relevant_objects": list(self.relevant_objects),
            "task_atoms": self.task_atoms,
            "required_final_atoms": self.required_final_atoms,
            "task_progress": dict(self.task_progress),
            "prompt": self.prompt,
            "raw_response": self.raw_response,
            "diagnostics": dict(self.diagnostics),
        }


def build_task_semantics_prompt(task: ParsedTask, graph: SceneGraph) -> str:
    objects = [
        {
            "name": node.name,
            "category": node.category,
            "affordances": node.affordances,
            "state": node.state,
            "geometry": {
                "kind": node.geometry.get("kind"),
                "half_extents": node.geometry.get("half_extents"),
                "mesh_path": node.geometry.get("mesh_path"),
            },
        }
        for node in graph.objects
    ]
    return (
        "You are a task semantics interpreter for a robot planner. "
        "The world facts come from simulation truth; do not invent geometry. "
        "Return JSON only with target_object, goal_object, task_atoms, required_final_atoms, "
        "task_progress, relevant_objects, and optional recovery_goal_candidates. "
        "Use predicates such as target, goal, goal_container, requires_final, on, inside, open, closed, holding. "
        "Every object name must be copied exactly from Objects. Do not invent object names, poses, grasps, or geometry. "
        "Atoms must use {\"predicate\": string, \"args\": [strings...]} format. "
        f"Task: {task.language}\n"
        f"Objects: {objects}\n"
        f"Table geometry: {graph.table_geometry}\n"
        f"World atoms: {graph.world_atoms}\n"
    )


def _name_contains(name: str, tokens: Iterable[str]) -> bool:
    low = name.lower().replace("_", " ")
    return any(tok in low for tok in tokens)


def _choose_name(names: Sequence[str], tokens: Iterable[str], avoid: Optional[str] = None) -> Optional[str]:
    token_list = list(tokens)
    for name in names:
        if avoid is not None and name == avoid:
            continue
        if _name_contains(name, token_list):
            return name
    return None


def _find_goal(task: ParsedTask, graph: SceneGraph, target: Optional[str]) -> Optional[str]:
    object_names = [node.name for node in graph.objects]
    if (
        task.goal_hint
        and task.goal_hint in object_names
        and task.goal_hint != target
        and (task.diagnostics or {}).get("goal_source") == "bddl"
    ):
        return task.goal_hint
    if language_requests_on_top(task.language) and "cabinet" in task.language.lower():
        cabinet_body = prefer_cabinet_body_name(object_names, avoid=target)
        if cabinet_body is not None:
            return cabinet_body
    if task.goal_hint and task.goal_hint in object_names and task.goal_hint != target:
        return task.goal_hint
    low = task.language.lower().replace("_", " ")
    priorities = [
        ("microwave", ("microwave",)),
        ("drawer", ("drawer",)),
        ("cabinet", ("cabinet",)),
        ("basket", ("basket",)),
        ("box", ("box",)),
        ("plate", ("plate",)),
        ("stove", ("stove",)),
        ("table", ("table",)),
    ]
    for key, tokens in priorities:
        if key in low:
            if key == "cabinet" and not language_requests_inside(task.language):
                found = prefer_cabinet_body_name(object_names, avoid=target)
            else:
                found = _choose_name(object_names, tokens, avoid=target)
            if found is not None:
                return found
    for node in graph.objects:
        if node.name != target and is_probably_surface(node.name):
            return node.name
    return None


def _find_door(goal: Optional[str], graph: SceneGraph) -> Optional[str]:
    if goal is None:
        return None
    names = [node.name for node in graph.objects]
    low = goal.lower()
    if "microwave" in low:
        return _choose_name(names, ("microdoorroot", "doorroot", "door"), avoid=goal)
    if "drawer" in low or "cabinet" in low:
        return _choose_name(names, ("door", "drawer"), avoid=goal)
    return None


def _has_atom(atoms: Sequence[Atom], predicate: str, *args: str) -> bool:
    key = (predicate, tuple(args))
    return any(atom_key(atom) == key for atom in atoms)


def _extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM task semantics response must be a JSON object")
    return value


def _coerce_atom(value: Any, object_names: Sequence[str], source: str) -> Optional[Atom]:
    if isinstance(value, dict):
        predicate = str(value.get("predicate", ""))
        args = value.get("args", [])
    elif isinstance(value, (list, tuple)) and value:
        predicate = str(value[0])
        args = list(value[1:])
    else:
        return None
    if predicate not in ALLOWED_TASK_PREDICATES:
        return None
    if not isinstance(args, (list, tuple)):
        return None
    clean_args = [str(arg) for arg in args]
    final_predicates = {"on", "inside", "open", "closed", "holding"}
    if predicate == "requires_final":
        if not clean_args or clean_args[0] not in final_predicates:
            return None
        check_args = clean_args[1:]
    else:
        check_args = clean_args
    object_set = set(object_names) | {"gripper", "table"}
    for arg in check_args:
        if arg not in object_set:
            return None
    return make_atom(predicate, *clean_args, source=source)


def _coerce_atoms(values: Any, object_names: Sequence[str], source: str) -> List[Atom]:
    if not isinstance(values, list):
        return []
    atoms: List[Atom] = []
    seen = set()
    for value in values:
        atom = _coerce_atom(value, object_names, source)
        if atom is None:
            continue
        key = atom_key(atom)
        if key in seen:
            continue
        seen.add(key)
        atoms.append(atom)
    return atoms


def _valid_optional_name(value: Any, object_names: Sequence[str]) -> Optional[str]:
    if value is None:
        return None
    object_set = set(object_names)
    if isinstance(value, (list, tuple)):
        for item in value:
            name = str(item)
            if name in object_set:
                return name
        return None
    name = str(value)
    return name if name in object_set else None


def _task_requires_inside(task: ParsedTask, goal: Optional[str]) -> bool:
    if language_requests_on_top(task.language):
        return False
    if language_requests_inside(task.language):
        return True
    # Cabinet is furniture: "on the cabinet" is On, not Inside.
    # Keep the name heuristic for true containers/drawers.
    if goal and any(token in goal.lower() for token in ("microwave", "drawer", "basket", "box")):
        return True
    return False


def _task_requires_closed(task: ParsedTask, goal: Optional[str]) -> bool:
    low = task.language.lower().replace("_", " ")
    return "close" in low or "closed" in low or "shut" in low


class RuleTaskSemanticsInterpreter:
    """Rule backend with the same IO contract expected from an LLM semantics backend."""

    def interpret(self, task: ParsedTask, graph: SceneGraph) -> TaskSemanticsResult:
        object_names = [node.name for node in graph.objects]
        target = task.target_hint if task.target_hint in object_names else None
        if target is None:
            target = _choose_name(object_names, ("mug", "bowl", "plate", "book", "object", "can", "bottle"))
        goal = _find_goal(task, graph, target)
        door = _find_door(goal, graph)
        requires_inside = _task_requires_inside(task, goal)
        requires_closed = _task_requires_closed(task, goal)

        task_atoms: List[Atom] = []
        required: List[Atom] = []
        relevant = [name for name in (target, goal, door) if name is not None]
        if target:
            task_atoms.append(make_atom("target", target, source="task_semantics"))
        if goal:
            goal_pred = "goal_container" if requires_inside else "goal_surface"
            task_atoms.append(make_atom(goal_pred, goal, source="task_semantics"))
            task_atoms.append(make_atom("goal", goal, source="task_semantics"))
        if task.operation == "pick" and target:
            required.append(make_atom("holding", "gripper", target, source="task_semantics"))
            task_atoms.append(make_atom("requires_final", "holding", "gripper", target, source="task_semantics"))
        elif target and goal:
            placement_pred = "inside" if requires_inside else "on"
            required.append(make_atom(placement_pred, target, goal, source="task_semantics"))
            task_atoms.append(make_atom("requires_final", placement_pred, target, goal, source="task_semantics"))
        if requires_closed and goal:
            required.append(make_atom("closed", goal, source="task_semantics"))
            task_atoms.append(make_atom("requires_final", "closed", goal, source="task_semantics"))

        target_grasped = bool(target and _has_atom(graph.world_atoms, "holding", "gripper", target))
        target_at_goal = False
        if target and goal:
            target_at_goal = _has_atom(graph.world_atoms, "inside" if requires_inside else "on", target, goal)
            if requires_inside and not target_at_goal:
                target_at_goal = _has_atom(graph.world_atoms, "on", target, goal)
        container_ready = True
        if goal and ("container" in object_affordances(goal) or requires_inside):
            container_ready = _has_atom(graph.world_atoms, "open", goal) or not requires_inside
        final_satisfied = []
        for atom in required:
            pred, args = atom_key(atom)
            satisfied = _has_atom(graph.world_atoms, pred, *args)
            if pred == "inside" and not satisfied:
                satisfied = _has_atom(graph.world_atoms, "on", *args)
            final_satisfied.append(satisfied)
        goal_completed = bool(required) and all(final_satisfied)

        if not target_grasped and target:
            next_subgoal = f"pick {target}"
        elif target_grasped and goal and not target_at_goal:
            next_subgoal = f"place {'inside' if requires_inside else 'on'} {goal}"
        elif target_at_goal and requires_closed and goal and not _has_atom(graph.world_atoms, "closed", goal):
            next_subgoal = f"close {goal}"
        elif goal_completed:
            next_subgoal = "handoff_to_vla"
        else:
            next_subgoal = "recover_to_safe_pose"

        progress = {
            "target_identified": target is not None,
            "goal_identified": goal is not None,
            "target_grasped": target_grasped,
            "target_at_goal": target_at_goal,
            "container_ready": container_ready,
            "requires_inside": requires_inside,
            "requires_closed": requires_closed,
            "goal_completed": goal_completed,
            "next_subgoal": next_subgoal,
        }
        return TaskSemanticsResult(
            target_object=target,
            goal_object=goal,
            relevant_objects=relevant,
            task_atoms=task_atoms,
            required_final_atoms=required,
            task_progress=progress,
            prompt=build_task_semantics_prompt(task, graph),
            diagnostics={
                "backend": "rule",
                "num_world_atoms": len(graph.world_atoms),
                "on_top_language": language_requests_on_top(task.language),
                "language_requests_inside": language_requests_inside(task.language),
                "goal_hint": task.goal_hint,
                "parser": dict(task.diagnostics or {}),
            },
        )


def build_rule_layer_record(
    parsed: ParsedTask,
    task_semantics: Optional[TaskSemanticsResult] = None,
    recovery_goals: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Compact snapshot of the rule parse / semantics / recovery-goal table."""
    goals_out: List[Dict[str, Any]] = []
    for goal in recovery_goals or []:
        if hasattr(goal, "to_dict"):
            goals_out.append(dict(goal.to_dict()))
        elif isinstance(goal, dict):
            goals_out.append(dict(goal))
    semantics = task_semantics.to_dict() if task_semantics is not None else {}
    return {
        "kind": "rule",
        "language": parsed.language,
        "operation": parsed.operation,
        "parser_target_hint": (parsed.diagnostics or {}).get("parser_target_hint"),
        "parser_goal_hint": (parsed.diagnostics or {}).get("parser_goal_hint"),
        "target_name": parsed.target_hint,
        "goal_name": parsed.goal_hint,
        "target_source": (parsed.diagnostics or {}).get("target_source", "parser"),
        "goal_source": (parsed.diagnostics or {}).get("goal_source", "parser"),
        "bddl_path": (parsed.diagnostics or {}).get("bddl_path"),
        "bddl_target": (parsed.diagnostics or {}).get("bddl_target"),
        "bddl_goal": (parsed.diagnostics or {}).get("bddl_goal"),
        "bddl_goal_atoms": (parsed.diagnostics or {}).get("bddl_goal_atoms") or [],
        "bddl_goal_surfaces": (parsed.diagnostics or {}).get("bddl_goal_surfaces") or [],
        "bddl_init_atoms": (parsed.diagnostics or {}).get("bddl_init_atoms") or [],
        "bddl_regions": (parsed.diagnostics or {}).get("bddl_regions") or {},
        "task_goal_source": (parsed.diagnostics or {}).get("task_goal_source", "bddl"),
        "goal_atoms": (parsed.diagnostics or {}).get("goal_atoms") or [],
        "goal_surfaces": (parsed.diagnostics or {}).get("goal_surfaces") or [],
        "goal_regions": (parsed.diagnostics or {}).get("goal_regions") or {},
        "semantics_target": semantics.get("target_object"),
        "semantics_goal": semantics.get("goal_object"),
        "required_final_atoms": semantics.get("required_final_atoms") or [],
        "recovery_goals": goals_out,
    }


class LLMTaskSemanticsInterpreter:
    """OpenAI-compatible backend for grounded task atoms and task progress."""

    def __init__(self, client: Optional[OpenAIResponsesClient] = None, cfg: Optional[LLMClientConfig] = None) -> None:
        self.client = client or OpenAIResponsesClient(cfg)

    def interpret(self, task: ParsedTask, graph: SceneGraph) -> TaskSemanticsResult:
        prompt = build_task_semantics_prompt(task, graph)
        raw = self.client.complete_json(
            prompt,
            system=(
                "You are the semantics module in a robot task-and-motion planner. "
                "Return strict JSON only. Use only object names and predicates provided by the user prompt."
            ),
        )
        data = _extract_json_object(raw)
        object_names = [node.name for node in graph.objects]
        object_set = set(object_names)
        target = _valid_optional_name(data.get("target_object"), object_names)
        goal = _valid_optional_name(data.get("goal_object"), object_names)
        relevant = [str(x) for x in data.get("relevant_objects", []) if str(x) in object_set]
        if target and target not in relevant:
            relevant.insert(0, target)
        if goal and goal not in relevant:
            relevant.append(goal)
        task_atoms = _coerce_atoms(data.get("task_atoms", []), object_names, "llm_task_semantics")
        required = _coerce_atoms(data.get("required_final_atoms", []), object_names, "llm_task_semantics")
        progress = data.get("task_progress", {})
        if not isinstance(progress, dict):
            progress = {}
        progress = dict(progress)
        progress.setdefault("target_identified", target is not None)
        progress.setdefault("goal_identified", goal is not None)
        progress.setdefault("next_subgoal", "recover_to_safe_pose")

        return TaskSemanticsResult(
            target_object=target,
            goal_object=goal,
            relevant_objects=relevant,
            task_atoms=task_atoms,
            required_final_atoms=required,
            task_progress=progress,
            prompt=prompt,
            raw_response=raw,
            diagnostics={
                "backend": "llm",
                "model": self.client.cfg.model,
                "base_url": self.client.cfg.base_url,
                "num_world_atoms": len(graph.world_atoms),
                "num_task_atoms": len(task_atoms),
                "num_required_final_atoms": len(required),
            },
        )
