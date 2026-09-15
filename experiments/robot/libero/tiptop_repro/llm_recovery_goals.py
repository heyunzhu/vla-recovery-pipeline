from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .affordances import is_probably_movable, is_probably_surface
from .llm_client import LLMClientConfig, OpenAIResponsesClient
from .predicates import SymbolicState
from .real_cutamp_adapter import RealCuTAMPRecoveryGoal
from .recovery_symbols import RecoverySymbolicAbstraction
from .scene_graph import SceneGraph
from .scene_reader import SceneState
from .tamp_scene import GroundedAtom
from .task_parser import ParsedTask
from .task_semantics import TaskSemanticsResult, _extract_json_object


ALLOWED_RECOVERY_TYPES = {
    "retreat_only",
    "regain_grasp",
    "safe_place_on_table",
    "finish_place",
    "reapproach_target",
    "unsupported",
}

ALLOWED_GOAL_PREDICATES = {"holding", "on", "inside", "handempty"}


@dataclass
class LLMRecoveryGoalDiagnostics:
    enabled: bool
    prompt: str = ""
    raw_response: str = ""
    accepted: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "prompt": self.prompt,
            "raw_response": self.raw_response,
            "accepted": list(self.accepted),
            "rejected": list(self.rejected),
            "error": self.error,
        }


class LLMRecoveryGoalGenerator:
    """Domain-aware LLM proposal stage for local recovery goals.

    The LLM is allowed to choose recovery intent and symbolic goal atoms only.
    Every proposal is validated against the current cuTAMP pick/place domain
    before it can be sent to the planner.
    """

    def __init__(self, client: Optional[OpenAIResponsesClient] = None, cfg: Optional[LLMClientConfig] = None) -> None:
        self.client = client or OpenAIResponsesClient(cfg)

    def propose(
        self,
        scene: SceneState,
        parsed: ParsedTask,
        sym: SymbolicState,
        graph: SceneGraph,
        task_semantics: TaskSemanticsResult | None,
        recovery: RecoverySymbolicAbstraction,
        max_goals: int = 6,
    ) -> Tuple[List[RealCuTAMPRecoveryGoal], LLMRecoveryGoalDiagnostics]:
        prompt = build_recovery_goal_prompt(scene, parsed, sym, graph, task_semantics, recovery, max_goals=max_goals)
        diag = LLMRecoveryGoalDiagnostics(enabled=True, prompt=prompt)
        try:
            raw = self.client.complete_json(
                prompt,
                system=(
                    "You are the recovery-goal module for a task-and-motion planner. "
                    "Return strict JSON only. Do not output robot actions or trajectories."
                ),
            )
            diag.raw_response = raw
            data = _extract_json_object(raw)
            proposals = data.get("recovery_goal_candidates", [])
            if not isinstance(proposals, list):
                proposals = []
            goals: List[RealCuTAMPRecoveryGoal] = []
            seen = set()
            for idx, proposal in enumerate(proposals[: max(1, max_goals)]):
                goal, rejection = validate_llm_recovery_goal(proposal, scene, idx)
                if goal is None:
                    diag.rejected.append(rejection)
                    continue
                key = tuple((atom.predicate, atom.args) for atom in goal.atoms)
                if key in seen:
                    diag.rejected.append({"idx": idx, "reason": "duplicate_goal_atoms", "proposal": proposal})
                    continue
                seen.add(key)
                goals.append(goal)
                diag.accepted.append(goal.to_dict())
            return goals, diag
        except Exception as exc:
            diag.error = str(exc)
            return [], diag


def build_recovery_goal_prompt(
    scene: SceneState,
    parsed: ParsedTask,
    sym: SymbolicState,
    graph: SceneGraph,
    task_semantics: TaskSemanticsResult | None,
    recovery: RecoverySymbolicAbstraction,
    max_goals: int = 6,
) -> str:
    movable_names = [name for name in scene.objects if is_probably_movable(name)]
    surface_names = ["table"] + [name for name in scene.objects if is_probably_surface(name)]
    object_summaries = [
        {
            "name": node.name,
            "category": node.category,
            "affordances": node.affordances,
            "dist_to_ee": node.dist_to_ee,
            "state": node.state,
        }
        for node in graph.objects
    ]
    semantics = task_semantics.to_dict() if task_semantics is not None else {}
    return (
        "Choose short-horizon recovery goals for cuTAMP after a VLA policy is judged risky or stuck.\n"
        "Important: output local recovery goals, not full robot action sequences.\n"
        "The downstream cuTAMP domain currently supports pick/place-style goals only:\n"
        "- Holding(obj), where obj must be in Movable objects.\n"
        "- On(obj, surface) or Inside(obj, surface), where obj must be movable and surface must be in Surfaces.\n"
        "- HandEmpty(), usually paired with a placement goal or used for retreat_only.\n"
        "Do not ask cuTAMP to hold or place drawers, cabinet parts, doors, robot links, fixtures, or table.\n"
        "If the problem is articulated/button/open/close and no valid pick/place recovery goal exists, return unsupported first.\n"
        "Prefer minimal disturbance: retreat_only or safe_place_on_table before finishing the whole task unless the finish is already close.\n"
        "Return JSON with key recovery_goal_candidates. Each item must have recovery_type, goal_atoms, target_object, goal_object, priority, reason.\n"
        f"Allowed recovery_type values: {sorted(ALLOWED_RECOVERY_TYPES)}.\n"
        f"Return at most {max_goals} candidates ordered by priority.\n"
        f"Task: {parsed.language}\n"
        f"Parsed target hint: {parsed.target_hint}; parsed goal hint: {parsed.goal_hint}; operation: {parsed.operation}\n"
        f"Symbolic target: {None if sym.target is None else sym.target.name}; symbolic goal: {None if sym.goal is None else sym.goal.name}\n"
        f"End effector: {scene.ee_pos[:3].astype(float).tolist()}; gripper_open: {scene.gripper_open}\n"
        f"Movable objects: {movable_names}\n"
        f"Surfaces: {surface_names}\n"
        f"Objects: {object_summaries}\n"
        f"World atoms: {graph.world_atoms}\n"
        f"Recovery atoms: {recovery.atoms}\n"
        f"Task semantics: {semantics}\n"
    )


def validate_llm_recovery_goal(
    proposal: Any,
    scene: SceneState,
    idx: int = 0,
) -> Tuple[Optional[RealCuTAMPRecoveryGoal], Dict[str, Any]]:
    if not isinstance(proposal, dict):
        return None, {"idx": idx, "reason": "proposal_not_object", "proposal": proposal}
    recovery_type = str(proposal.get("recovery_type", ""))
    if recovery_type not in ALLOWED_RECOVERY_TYPES:
        return None, {"idx": idx, "reason": "bad_recovery_type", "proposal": proposal}
    if recovery_type == "unsupported":
        return None, {"idx": idx, "reason": "unsupported_by_domain", "proposal": proposal}
    raw_atoms = proposal.get("goal_atoms", [])
    if not isinstance(raw_atoms, list):
        return None, {"idx": idx, "reason": "goal_atoms_not_list", "proposal": proposal}

    atoms: List[GroundedAtom] = []
    surface_names: List[str] = []
    seen = set()
    for raw_atom in raw_atoms:
        atom = _coerce_goal_atom(raw_atom, scene)
        if atom is None:
            return None, {"idx": idx, "reason": "invalid_goal_atom", "atom": raw_atom, "proposal": proposal}
        key = (atom.predicate, atom.args)
        if key in seen:
            continue
        seen.add(key)
        atoms.append(atom)
        if atom.predicate in {"on", "inside"}:
            surface_names.append(atom.args[1])
    if not atoms:
        return None, {"idx": idx, "reason": "empty_goal_atoms", "proposal": proposal}

    unique_surfaces = _unique_surfaces(surface_names)
    reason = str(proposal.get("reason", "llm proposed domain-aware recovery goal"))
    priority = proposal.get("priority", None)
    name = f"llm_{idx}_{recovery_type}"
    if isinstance(priority, (int, float)):
        name = f"{name}_{float(priority):.2f}".replace(".", "p")
    return RealCuTAMPRecoveryGoal(name=name, atoms=atoms, surface_names=unique_surfaces, reason=reason), {}


def _coerce_goal_atom(raw_atom: Any, scene: SceneState) -> Optional[GroundedAtom]:
    if isinstance(raw_atom, dict):
        predicate = str(raw_atom.get("predicate", "")).lower()
        args = raw_atom.get("args", [])
    elif isinstance(raw_atom, (list, tuple)) and raw_atom:
        predicate = str(raw_atom[0]).lower()
        args = list(raw_atom[1:])
    else:
        return None
    if predicate == "inside":
        predicate = "inside"
    if predicate not in ALLOWED_GOAL_PREDICATES:
        return None
    if not isinstance(args, (list, tuple)):
        return None
    clean_args = tuple(str(arg) for arg in args)
    if predicate == "handempty":
        return GroundedAtom("handempty", ())
    if predicate == "holding" and len(clean_args) == 1:
        obj = clean_args[0]
        if obj in scene.objects and is_probably_movable(obj):
            return GroundedAtom("holding", (obj,))
        return None
    if predicate == "holding" and len(clean_args) == 2 and clean_args[0] == "gripper":
        obj = clean_args[1]
        if obj in scene.objects and is_probably_movable(obj):
            return GroundedAtom("holding", (obj,))
        return None
    if predicate in {"on", "inside"} and len(clean_args) == 2:
        obj, surface = clean_args
        if obj not in scene.objects or not is_probably_movable(obj):
            return None
        if surface != "table" and (surface not in scene.objects or not is_probably_surface(surface)):
            return None
        return GroundedAtom(predicate, (obj, surface))
    return None


def _unique_surfaces(names: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out
