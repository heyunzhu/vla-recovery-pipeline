"""Duck-typed hook bridge for the execution layer. Executor must not import this module."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .capabilities import CapabilityRegistry, add_capability_audit_to_hints, load_capability_registry
from .dispatcher import BackendDecision, dispatch, merge_recovery_hints
from .geometry_profiles import GeometryProfileRegistry, load_geometry_profile_registry
from .grounding_profiles import GroundingProfileRegistry, load_grounding_profile_registry
from .hooks import HookBus
from .matcher import Match, diagnose_skills, match_recovery_hints
from .place_profiles import PlaceProfileRegistry, load_place_profile_registry
from .predicate_registry import PredicateRegistry, load_predicate_registry
from .repair_profiles import RepairProfileRegistry, load_repair_profile_registry
from .schema import SkillSchemaError, SkillSpec, resolve_online_skills
from experiments.robot.libero.tiptop_repro.grasp_profiles import (
    GRASP_PROFILE_ADAPTER_PARAM_KEY,
    GraspProfileRegistry,
    load_grasp_profile_registry,
)


class SkillRuntime:
    def __init__(
        self,
        skills: list[SkillSpec] | None = None,
        *,
        capability_registry: CapabilityRegistry | None = None,
        repair_profile_registry: RepairProfileRegistry | None = None,
        place_profile_registry: PlaceProfileRegistry | None = None,
        grasp_profile_registry: GraspProfileRegistry | None = None,
        grounding_profile_registry: GroundingProfileRegistry | None = None,
        geometry_profile_registry: GeometryProfileRegistry | None = None,
        predicate_registry: PredicateRegistry | None = None,
    ) -> None:
        self.skills = list(skills or [])
        self.predicate_registry = predicate_registry or next(
            (
                getattr(skill, "predicate_registry", None)
                for skill in self.skills
                if getattr(skill, "predicate_registry", None) is not None
            ),
            PredicateRegistry.builtins(),
        )
        self.capability_registry = capability_registry or CapabilityRegistry.allow_all()
        self.repair_profile_registry = repair_profile_registry or RepairProfileRegistry.disabled()
        self.place_profile_registry = place_profile_registry or PlaceProfileRegistry.disabled()
        self.grasp_profile_registry = grasp_profile_registry or GraspProfileRegistry.disabled()
        self.grounding_profile_registry = grounding_profile_registry or GroundingProfileRegistry.disabled()
        self.geometry_profile_registry = geometry_profile_registry or GeometryProfileRegistry.disabled()
        self.bus = HookBus(self.skills, predicate_registry=self.predicate_registry)
        self.last_state: dict[str, Any] = {}
        self.ee_history: list[list[float]] = []
        self.last_match: Match | None = None
        self.last_decision: BackendDecision | None = None
        self.last_hook_diagnostics: list[dict[str, Any]] = []

    @classmethod
    def from_index(
        cls,
        index_path: str | Path,
        *,
        capability_registry: CapabilityRegistry | None = None,
        repair_profile_registry: RepairProfileRegistry | None = None,
        place_profile_registry: PlaceProfileRegistry | None = None,
        grasp_profile_registry: GraspProfileRegistry | None = None,
        grounding_profile_registry: GroundingProfileRegistry | None = None,
        geometry_profile_registry: GeometryProfileRegistry | None = None,
        predicate_registry: PredicateRegistry | None = None,
    ) -> "SkillRuntime":
        predicates = predicate_registry or load_predicate_registry(index_path=index_path)
        registry = capability_registry or load_capability_registry(index_path=index_path)
        repair_profiles = repair_profile_registry or load_repair_profile_registry(index_path=index_path)
        profiles = place_profile_registry or load_place_profile_registry(index_path=index_path)
        grasps = grasp_profile_registry or load_grasp_profile_registry(index_path=index_path)
        grounding_profiles = grounding_profile_registry or load_grounding_profile_registry(index_path=index_path)
        geometry_profiles = geometry_profile_registry or load_geometry_profile_registry(index_path=index_path)
        return cls(
            resolve_online_skills(index_path, predicate_registry=predicates),
            capability_registry=registry,
            repair_profile_registry=repair_profiles,
            place_profile_registry=profiles,
            grasp_profile_registry=grasps,
            grounding_profile_registry=grounding_profiles,
            geometry_profile_registry=geometry_profiles,
            predicate_registry=predicates,
        )

    def _merge(self, state: Mapping[str, Any]) -> dict[str, Any]:
        merged = {**self.last_state, **dict(state)}
        xyz = merged.get("ee_xyz")
        if isinstance(xyz, (list, tuple)) and len(xyz) >= 3:
            self.ee_history.append([float(xyz[0]), float(xyz[1]), float(xyz[2])])
            self.ee_history = self.ee_history[-16:]
        merged["ee_history"] = list(self.ee_history)
        if "aperture" not in merged and merged.get("gripper_aperture") is not None:
            merged["aperture"] = merged.get("gripper_aperture")
        self.last_state.update(merged)
        return merged

    def _apply_capability_gate(self, recovery_hints: Mapping[str, Any] | None) -> dict[str, Any]:
        audit = self.capability_registry.audit_recovery_hints(recovery_hints)
        if audit.errors:
            raise SkillSchemaError(
                "capability registry rejected recovery hints: " + "; ".join(audit.errors)
            )
        if self.capability_registry.enabled:
            return add_capability_audit_to_hints(recovery_hints, audit)
        return dict(recovery_hints or {})

    def _attach_grasp_profile_adapter(self, recovery_hints: Mapping[str, Any] | None) -> dict[str, Any]:
        hints = dict(recovery_hints or {})
        if not hints.get("grasp_profile") or not self.grasp_profile_registry.enabled:
            return hints
        params = dict(hints.get("params") or {})
        adapter_paths = [
            adapter.path
            for adapter in self.grasp_profile_registry.adapters
            if hints.get("grasp_profile") in adapter.profile_ids
        ]
        if adapter_paths:
            params[GRASP_PROFILE_ADAPTER_PARAM_KEY] = adapter_paths[0] if len(adapter_paths) == 1 else adapter_paths
            hints["params"] = params
        return hints

    def _expand_place_profiles(self, recovery_hints: Mapping[str, Any] | None) -> dict[str, Any]:
        expanded = self.place_profile_registry.expand_recovery_hints(recovery_hints)
        params = expanded.get("params") if isinstance(expanded.get("params"), Mapping) else {}
        if (
            isinstance(params, Mapping)
            and params.get("place_profile")
            and not self.place_profile_registry.enabled
            and self.capability_registry.enabled
        ):
            raise SkillSchemaError("place_profile requires a loaded place profile registry")
        return expanded

    def _expand_repair_profiles(self, recovery_hints: Mapping[str, Any] | None) -> dict[str, Any]:
        expanded = self.repair_profile_registry.expand_recovery_hints(recovery_hints)
        params = expanded.get("params") if isinstance(expanded.get("params"), Mapping) else {}
        if (
            isinstance(params, Mapping)
            and params.get("repair_profile")
            and not self.repair_profile_registry.enabled
            and self.capability_registry.enabled
        ):
            raise SkillSchemaError("repair_profile requires a loaded repair profile registry")
        return expanded

    def _expand_grounding_profiles(self, recovery_hints: Mapping[str, Any] | None) -> dict[str, Any]:
        expanded = self.grounding_profile_registry.expand_recovery_hints(recovery_hints)
        params = expanded.get("params") if isinstance(expanded.get("params"), Mapping) else {}
        if (
            isinstance(params, Mapping)
            and params.get("grounding_profile")
            and not self.grounding_profile_registry.enabled
            and self.capability_registry.enabled
        ):
            raise SkillSchemaError("grounding_profile requires a loaded grounding profile registry")
        return expanded

    def _expand_geometry_profiles(self, recovery_hints: Mapping[str, Any] | None) -> dict[str, Any]:
        expanded = self.geometry_profile_registry.expand_recovery_hints(recovery_hints)
        params = expanded.get("params") if isinstance(expanded.get("params"), Mapping) else {}
        if (
            isinstance(params, Mapping)
            and params.get("geometry_profile")
            and not self.geometry_profile_registry.enabled
            and self.capability_registry.enabled
        ):
            raise SkillSchemaError("geometry_profile requires a loaded geometry profile registry")
        return expanded

    def _expand_named_profiles(self, recovery_hints: Mapping[str, Any] | None) -> dict[str, Any]:
        hints = self._expand_grounding_profiles(recovery_hints)
        hints = self._expand_geometry_profiles(hints)
        hints = self._expand_repair_profiles(hints)
        return self._expand_place_profiles(hints)

    def _emit(self, hook: str, state: Mapping[str, Any]) -> dict[str, Any] | None:
        merged = self._merge(state)
        self.last_hook_diagnostics = diagnose_skills(
            self.skills,
            hook,
            merged,
            predicate_registry=self.predicate_registry,
        )
        match = self.bus.emit(hook, merged)
        self.last_match = match
        if match is None:
            self.last_decision = None
            return None
        decision = dispatch(match, merged)
        if decision.enter_recovery:
            sources = [(match.skill.id, int(match.skill.priority), dict(decision.recovery_hints or {}))]
            sources.extend(
                (hint.skill.id, int(hint.skill.priority), dict(hint.skill.recovery_hints or {}))
                for hint in match_recovery_hints(
                    self.skills,
                    merged,
                    predicate_registry=self.predicate_registry,
                )
            )
            decision.recovery_hints = merge_recovery_hints(sources)
            decision.recovery_hints = self._expand_named_profiles(decision.recovery_hints)
            decision.recovery_hints = self._apply_capability_gate(decision.recovery_hints)
            decision.recovery_hints = self._attach_grasp_profile_adapter(decision.recovery_hints)
            params = dict(decision.recovery_hints.get("params") or {})
            decision.hint_sources = list(params.get("hint_sources") or [])
        self.last_decision = decision
        return decision.to_dict()

    def force_recovery_query(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Enter recovery for CLI ablations while still applying hint policies."""
        merged = self._merge(state)
        sources = [
            (hint.skill.id, int(hint.skill.priority), dict(hint.skill.recovery_hints or {}))
            for hint in match_recovery_hints(
                self.skills,
                merged,
                predicate_registry=self.predicate_registry,
            )
        ]
        hints = merge_recovery_hints(sources)
        hints = self._expand_named_profiles(hints)
        hints = self._apply_capability_gate(hints)
        hints = self._attach_grasp_profile_adapter(hints)
        params = dict(hints.get("params") or {})
        hint_sources = list(params.get("hint_sources") or [])
        skill_id = "force_recovery_query"
        if hint_sources:
            skill_id = f"{skill_id}:{hint_sources[-1].get('skill_id')}"
        decision = BackendDecision(
            enter_recovery=True,
            skill_id=skill_id,
            backend="force_recovery_query",
            recovery_hints=hints,
            hint_sources=hint_sources,
        )
        self.last_match = None
        self.last_decision = decision
        return decision.to_dict()

    def after_pi0_query(self, state: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._emit("after_pi0_query", state)

    def after_gripper_close(self, state: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._emit("after_gripper_close", state)

    def before_trajectory_step(self, state: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._emit("before_trajectory_step", state)

    def after_recovery_attempt(self, state: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._emit("after_recovery_attempt", state)
