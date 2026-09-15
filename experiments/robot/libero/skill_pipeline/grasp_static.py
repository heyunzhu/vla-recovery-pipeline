"""Static checks for grasp recovery-hint skills.

The schema layer answers "can this skill be parsed?".  This module answers a
narrower engineering question: "is this grasp hint safe to keep in the online
library?".  It checks catalog hygiene, hint boundaries, profile sampling, and a
small set of canary states that catch broad or ambiguous target matching.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from experiments.robot.libero.tiptop_repro.grasp_profiles import (
    GraspProfileRegistry,
    load_grasp_profile_registry,
    profile_gripper_width,
    sample_grasp_profile,
    sample_grasp_profile_xyzrpy,
    normalize_grasp_sampler_profile,
    is_native_grasp_sampler_profile,
)

from .matcher import eval_applies_to
from .schema import (
    SkillSchemaError,
    SkillSpec,
    load_index,
    load_skill,
    normalize_predicates,
    parse_front_matter,
    resolve_online_skills,
)

GRASP_SKILL_REL_DIR = "pair/recovery_hint/grasp"
NON_ONLINE_STATUSES = frozenset({"draft", "retired", "archived", "experimental"})
ALLOWED_GRASP_PARAM_KEYS = frozenset({"source", "executor"})
FORBIDDEN_GRASP_PARAM_KEYS = frozenset(
    {
        "grounding_hints",
        "geometry_hints",
        "placement_region",
        "placement_surface",
        "support_object",
        "place_candidate_policy",
        "place_yaw_policy",
    }
)
GRASP_EXECUTOR_RANGES = {
    "grasp_close_max_above_m": (0.03, 0.22),
    "grasp_lift_probe_m": (0.0, 0.10),
    "grasp_lift_probe_max_steps": (0, 60),
    "grasp_lift_follow_m": (0.001, 0.08),
    # Existing mug/white-bowl grasp hints use these to keep a confirmed grasp
    # high enough during transfer.  They are allowed here but should remain
    # transport-safety knobs, not placement-region logic.
    "place_hover_clearance_m": (0.0, 0.20),
    "place_lift_min_clearance_m": (0.0, 0.15),
    "place_lift_max_steps": (0, 80),
}
MAX_GRASP_SAMPLE_COUNT = 64


@dataclass(frozen=True)
class GraspStaticFinding:
    severity: str
    code: str
    message: str
    skill_id: str = ""
    path: str = ""
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "skill_id": self.skill_id,
            "path": self.path,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class GraspCanary:
    name: str
    state: Mapping[str, Any]
    expected_winner: str
    expected_profile: str


@dataclass(frozen=True)
class GraspCanaryResult:
    name: str
    expected_winner: str
    expected_profile: str
    matched_skill_ids: tuple[str, ...]
    winner_skill_id: str
    winner_profile: str

    @property
    def passed(self) -> bool:
        return self.winner_skill_id == self.expected_winner and self.winner_profile == self.expected_profile

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "expected_winner": self.expected_winner,
            "expected_profile": self.expected_profile,
            "matched_skill_ids": list(self.matched_skill_ids),
            "winner_skill_id": self.winner_skill_id,
            "winner_profile": self.winner_profile,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class GraspProfileSummary:
    skill_id: str
    profile: str
    sample_count: int
    gripper_width_m: float
    sample_modes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "profile": self.profile,
            "sample_count": self.sample_count,
            "gripper_width_m": self.gripper_width_m,
            "sample_modes": list(self.sample_modes),
        }


@dataclass(frozen=True)
class GraspStaticReport:
    index_path: str
    online_grasp_skill_ids: tuple[str, ...]
    checked_grasp_skill_ids: tuple[str, ...]
    profile_summaries: tuple[GraspProfileSummary, ...]
    canary_results: tuple[GraspCanaryResult, ...]
    findings: tuple[GraspStaticFinding, ...]

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "ERROR")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "WARN")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_path": self.index_path,
            "online_grasp_skill_ids": list(self.online_grasp_skill_ids),
            "checked_grasp_skill_ids": list(self.checked_grasp_skill_ids),
            "profile_summaries": [item.to_dict() for item in self.profile_summaries],
            "canary_results": [item.to_dict() for item in self.canary_results],
            "findings": [item.to_dict() for item in self.findings],
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


DEFAULT_GRASP_CANARIES = (
    GraspCanary(
        name="black_bowl_generic",
        state={
            "target_name": "akita_black_bowl_1_main",
            "task_description": "put the black bowl on the plate",
        },
        expected_winner="grasp_bowl_rim_diagonal_mixed_topdown",
        expected_profile="bowl_rim_diagonal_mixed_topdown_v1",
    ),
    GraspCanary(
        name="black_bowl_cabinet_top",
        state={
            "target_name": "akita_black_bowl_1_main",
            "task_description": "put the black bowl on top of the cabinet",
        },
        expected_winner="grasp_bowl_rim_away_from_open_drawer_topdown",
        expected_profile="bowl_rim_away_from_open_drawer_topdown_v1",
    ),
    GraspCanary(
        name="white_bowl_plate",
        state={
            "target_name": "white_bowl_1_main",
            "task_description": "put the white bowl on the plate",
        },
        expected_winner="grasp_small_shallow_bowl_rim_diagonal_topdown",
        expected_profile="bowl_rim_small_shallow_diagonal_topdown_v1",
    ),
    GraspCanary(
        name="white_bowl_right_plate",
        state={
            "target_name": "white_bowl_1_main",
            "task_description": "put the white bowl to the right of the plate",
        },
        expected_winner="grasp_task38_white_bowl_microwave_high_lift",
        expected_profile="bowl_rim_small_shallow_diagonal_topdown_v1",
    ),
    GraspCanary(
        name="cream_cheese_flat_box",
        state={"target_name": "cream_cheese_1_main"},
        expected_winner="grasp_flat_box_topdown_short_side_deep",
        expected_profile="flat_box_topdown_short_side_deep_v1",
    ),
    GraspCanary(
        name="chocolate_pudding_flat_box",
        state={"target_name": "chocolate_pudding_1_main"},
        expected_winner="grasp_flat_box_topdown_short_side_deep",
        expected_profile="flat_box_topdown_short_side_deep_v1",
    ),
    GraspCanary(
        name="book_caddy",
        state={"target_name": "black_book_1_main"},
        expected_winner="grasp_book_upright_topdown",
        expected_profile="flat_box_topdown_short_side_book_v1",
    ),
    GraspCanary(
        name="alphabet_soup_can",
        state={"target_name": "alphabet_soup_1_main"},
        expected_winner="grasp_can_body_lower_side",
        expected_profile="can_body_lower_side_v1",
    ),
    GraspCanary(
        name="tomato_sauce_can",
        state={"target_name": "tomato_sauce_1_main"},
        expected_winner="grasp_tomato_sauce_can_body_orthogonal_lower",
        expected_profile="can_body_orthogonal_lower_side_v1",
    ),
    GraspCanary(
        name="milk_upright",
        state={"target_name": "milk_1_main", "target_orientation": "upright"},
        expected_winner="grasp_carton_upright_body_side",
        expected_profile="carton_upright_body_side_v1",
    ),
    GraspCanary(
        name="milk_fallen",
        state={"target_name": "milk_1_main", "target_orientation": "fallen"},
        expected_winner="grasp_carton_fallen_body_side",
        expected_profile="carton_fallen_body_side_v1",
    ),
    GraspCanary(
        name="mug_or_cup",
        state={"target_name": "porcelain_mug_1_main"},
        expected_winner="grasp_mug_body_side_avoid_handle",
        expected_profile="mug_body_side_avoid_handle_v1",
    ),
    GraspCanary(
        name="moka_pot",
        state={"target_name": "moka_pot_1_main"},
        expected_winner="grasp_moka_pot_handle_topdown",
        expected_profile="moka_pot_handle_topdown_v1",
    ),
)


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _predicate_values(applies_to: Mapping[str, Any], predicate: str) -> list[Any]:
    values: list[Any] = []
    for group in ("all", "any"):
        for name, value in normalize_predicates(applies_to.get(group)):
            if name == predicate:
                values.append(value)
    return values


def _flatten_keys(node: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path
            yield from _flatten_keys(value, path)
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            yield from _flatten_keys(value, f"{prefix}[{idx}]")


def _profile_fixture(profile: str, registry: GraspProfileRegistry | None = None) -> tuple[tuple[float, float, float], bool, list[float]]:
    normalized = normalize_grasp_sampler_profile(profile, registry=registry)
    pose = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    if "bowl" in normalized:
        return (0.12, 0.12, 0.05), True, pose
    if "mug" in normalized:
        return (0.08, 0.08, 0.09), True, pose
    if "moka_pot" in normalized:
        return (0.10, 0.08, 0.12), False, pose
    if "can" in normalized:
        return (0.063, 0.063, 0.076), False, pose
    if "carton" in normalized:
        return (0.055, 0.055, 0.131), False, pose
    if "book" in normalized:
        return (0.10, 0.058, 0.136), False, pose
    if "flat_box" in normalized or "box" in normalized:
        return (0.087, 0.062, 0.018), False, pose
    return (0.06, 0.06, 0.04), False, pose


def _mode_values(samples: Sequence[Any]) -> tuple[str, ...]:
    modes: set[str] = set()
    for sample in samples:
        metadata = getattr(sample, "metadata", {}) or {}
        for key in ("grasp_intent", "mug_mode", "carton_mode", "can_mode", "open_drawer_point_id"):
            value = metadata.get(key)
            if value not in (None, ""):
                modes.add(f"{key}={value}")
        if metadata.get("book_thin_side_only"):
            modes.add("book_thin_side_only")
        if metadata.get("deep"):
            modes.add("deep")
    return tuple(sorted(modes))


def _finding(
    findings: list[GraspStaticFinding],
    severity: str,
    code: str,
    message: str,
    *,
    skill: SkillSpec | None = None,
    path: str = "",
    detail: Mapping[str, Any] | None = None,
) -> None:
    findings.append(
        GraspStaticFinding(
            severity=severity,
            code=code,
            message=message,
            skill_id="" if skill is None else skill.id,
            path=path or ("" if skill is None else skill.path),
            detail=dict(detail or {}),
        )
    )


def _check_catalog(skills_root: Path, online_rels: set[str], findings: list[GraspStaticFinding]) -> None:
    grasp_dir = skills_root / GRASP_SKILL_REL_DIR
    if not grasp_dir.is_dir():
        _finding(findings, "ERROR", "missing_grasp_dir", f"missing grasp skill directory: {grasp_dir}")
        return

    for rel in sorted(rel for rel in online_rels if rel.startswith(f"{GRASP_SKILL_REL_DIR}/")):
        path = skills_root / rel
        if not path.is_file():
            _finding(findings, "ERROR", "missing_online_grasp_file", "online grasp skill file is missing", path=rel)

    for path in sorted(grasp_dir.glob("*.md")):
        rel = _rel(path, skills_root)
        try:
            data, _body = parse_front_matter(path.read_text(encoding="utf-8"))
        except SkillSchemaError as exc:
            _finding(findings, "ERROR", "bad_front_matter", str(exc), path=rel)
            continue
        status = str(data.get("status") or "").strip().lower()
        if rel not in online_rels and status not in NON_ONLINE_STATUSES:
            _finding(
                findings,
                "ERROR",
                "unregistered_grasp_skill_file",
                "pair grasp skill file is not online and has no draft/retired status",
                path=rel,
                detail={"status": status or "<missing>"},
            )
        if rel in online_rels and status in NON_ONLINE_STATUSES:
            _finding(
                findings,
                "ERROR",
                "non_online_status_in_online_index",
                "online grasp skill is marked as draft/retired/experimental",
                path=rel,
                detail={"status": status},
            )


def _check_executor_params(spec: SkillSpec, findings: list[GraspStaticFinding]) -> None:
    params = spec.recovery_hints.get("params") or {}
    if not isinstance(params, Mapping):
        return
    unknown_params = sorted(set(params) - ALLOWED_GRASP_PARAM_KEYS)
    if unknown_params:
        _finding(
            findings,
            "WARN",
            "unknown_grasp_param_key",
            "grasp skill has non-standard recovery_hints.params keys",
            skill=spec,
            detail={"keys": unknown_params},
        )
    forbidden_paths = [
        key_path
        for key_path in _flatten_keys(params)
        if key_path.split(".")[-1] in FORBIDDEN_GRASP_PARAM_KEYS
    ]
    if forbidden_paths:
        _finding(
            findings,
            "ERROR",
            "grasp_hint_crosses_grounding_or_place_boundary",
            "grasp skill contains grounding/geometry/place hint keys",
            skill=spec,
            detail={"paths": forbidden_paths},
        )
    executor = params.get("executor") or {}
    if executor in (None, ""):
        return
    if not isinstance(executor, Mapping):
        _finding(findings, "ERROR", "bad_grasp_executor_params", "executor params must be a mapping", skill=spec)
        return
    for key, value in sorted(executor.items()):
        if key not in GRASP_EXECUTOR_RANGES:
            _finding(
                findings,
                "ERROR",
                "unknown_grasp_executor_key",
                "grasp skill uses an executor key outside the grasp allowlist",
                skill=spec,
                detail={"key": key},
            )
            continue
        low, high = GRASP_EXECUTOR_RANGES[key]
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            _finding(
                findings,
                "ERROR",
                "non_numeric_grasp_executor_value",
                "grasp executor value must be numeric",
                skill=spec,
                detail={"key": key, "value": value},
            )
            continue
        if numeric < float(low) or numeric > float(high):
            _finding(
                findings,
                "ERROR",
                "grasp_executor_value_out_of_range",
                "grasp executor value falls outside the executor clamp range",
                skill=spec,
                detail={"key": key, "value": numeric, "range": [low, high]},
            )


def _check_matching_scope(spec: SkillSpec, findings: list[GraspStaticFinding]) -> None:
    target_matches = [str(item) for item in _predicate_values(spec.applies_to, "target_name_matches")]
    target_excludes = [str(item) for item in _predicate_values(spec.applies_to, "target_name_excludes")]
    task_matches = [str(item) for item in _predicate_values(spec.applies_to, "task_language_matches")]
    orientation = _predicate_values(spec.applies_to, "target_orientation_is")
    profile = str(spec.recovery_hints.get("grasp_profile") or "")

    if not target_matches:
        _finding(
            findings,
            "ERROR",
            "grasp_missing_target_name_match",
            "grasp skill must bind a target object class with target_name_matches",
            skill=spec,
            detail={"task_language_matches": task_matches},
        )
    for pattern in target_matches:
        stripped = pattern.strip()
        if stripped in {".*", ".+", "(.*)", "(.+)"}:
            _finding(
                findings,
                "ERROR",
                "grasp_target_match_too_broad",
                "grasp target_name_matches is too broad for a grasp profile",
                skill=spec,
                detail={"pattern": pattern},
            )
    if task_matches and not target_matches:
        _finding(
            findings,
            "ERROR",
            "grasp_task_language_only_scope",
            "task-language-only scope is not allowed for grasp skills",
            skill=spec,
        )
    if "carton" in profile and not orientation:
        _finding(
            findings,
            "ERROR",
            "carton_grasp_missing_orientation_scope",
            "carton grasp profiles must declare target_orientation_is",
            skill=spec,
            detail={"profile": profile},
        )
    if "white" not in profile and any("bowl" in item and "white" not in item for item in target_matches):
        if not any("white_bowl" in item or "white bowl" in item for item in target_excludes):
            _finding(
                findings,
                "ERROR",
                "generic_bowl_grasp_must_exclude_white_bowl",
                "generic bowl grasp skills must exclude white_bowl so shallow-bowl skills stay unambiguous",
                skill=spec,
            )
    if not target_excludes and any("|" in item or ".*" in item for item in target_matches):
        _finding(
            findings,
            "WARN",
            "grasp_scope_has_no_excludes",
            "broad grasp target pattern has no target_name_excludes",
            skill=spec,
            detail={"target_name_matches": target_matches},
        )


def _check_profile_sampling(
    spec: SkillSpec,
    findings: list[GraspStaticFinding],
    *,
    registry: GraspProfileRegistry | None = None,
) -> GraspProfileSummary | None:
    profile = str(spec.recovery_hints.get("grasp_profile") or "")
    if not profile:
        _finding(findings, "ERROR", "grasp_missing_profile", "grasp skill must set recovery_hints.grasp_profile", skill=spec)
        return None
    try:
        normalized = normalize_grasp_sampler_profile(profile, registry=registry)
    except ValueError as exc:
        _finding(findings, "ERROR", "unknown_grasp_profile", str(exc), skill=spec, detail={"profile": profile})
        return None
    if is_native_grasp_sampler_profile(normalized, registry=registry):
        _finding(
            findings,
            "WARN",
            "native_grasp_profile_in_skill",
            "native cuTAMP grasp sampling is hard to audit; prefer a named shared profile",
            skill=spec,
            detail={"profile": normalized},
        )
        return GraspProfileSummary(spec.id, normalized, 0, 0.0)

    dims, rim, pose = _profile_fixture(normalized, registry=registry)
    try:
        samples = sample_grasp_profile(normalized, dims, rim=rim, pose=pose, registry=registry)
        xyzrpy = sample_grasp_profile_xyzrpy(normalized, dims, rim=rim, pose=pose, registry=registry)
        width = profile_gripper_width(normalized, dims, rim=rim, pose=pose, registry=registry)
    except Exception as exc:
        _finding(
            findings,
            "ERROR",
            "grasp_profile_sampling_failed",
            "shared grasp profile sampling failed",
            skill=spec,
            detail={"profile": normalized, "error": f"{type(exc).__name__}: {exc}"},
        )
        return None

    if not samples:
        _finding(findings, "ERROR", "empty_grasp_profile", "grasp profile produced no samples", skill=spec)
    if len(samples) != len(xyzrpy):
        _finding(
            findings,
            "ERROR",
            "grasp_xyzrpy_adapter_mismatch",
            "sample_grasp_profile and sample_grasp_profile_xyzrpy returned different counts",
            skill=spec,
            detail={"sample_count": len(samples), "xyzrpy_count": len(xyzrpy)},
        )
    if len(samples) > MAX_GRASP_SAMPLE_COUNT:
        _finding(
            findings,
            "WARN",
            "large_grasp_candidate_set",
            "grasp profile has many candidates; consider a smaller, explainable profile",
            skill=spec,
            detail={"sample_count": len(samples), "max": MAX_GRASP_SAMPLE_COUNT},
        )
    for idx, sample in enumerate(samples):
        values = [*sample.xyz, *sample.rpy]
        if not all(math.isfinite(float(value)) for value in values):
            _finding(
                findings,
                "ERROR",
                "nonfinite_grasp_sample",
                "grasp profile produced a non-finite xyz/rpy value",
                skill=spec,
                detail={"sample_index": idx, "values": values},
            )
            break
    if not math.isfinite(float(width)) or not (0.015 <= float(width) <= 0.090):
        _finding(
            findings,
            "ERROR",
            "invalid_grasp_gripper_width",
            "profile_gripper_width returned a value outside the Panda gripper sanity range",
            skill=spec,
            detail={"width": width},
        )
    return GraspProfileSummary(
        skill_id=spec.id,
        profile=normalized,
        sample_count=len(samples),
        gripper_width_m=float(width),
        sample_modes=_mode_values(samples),
    )


def _check_shared_profile_consumers(skills_root: Path, findings: list[GraspStaticFinding]) -> None:
    repo_root = skills_root.parent
    for candidate in (skills_root, *skills_root.parents):
        if (candidate / "experiments" / "robot" / "libero" / "tiptop_repro").is_dir():
            repo_root = candidate
            break
    required = {
        "experiments/robot/libero/tiptop_repro/tamp_scene.py": "sample_grasp_profile",
        "experiments/robot/libero/tiptop_repro/real_cutamp_backend.py": "sample_grasp_profile_xyzrpy",
    }
    for rel, needle in required.items():
        path = repo_root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "grasp_profiles import" not in text or needle not in text:
            _finding(
                findings,
                "ERROR",
                "grasp_profile_consumer_not_shared",
                "grasp profile consumer must import and use the shared grasp_profiles module",
                path=rel,
                detail={"required_symbol": needle},
            )


def _evaluate_canaries(skills: Sequence[SkillSpec]) -> tuple[GraspCanaryResult, ...]:
    ranked = sorted(skills, key=lambda skill: (int(skill.priority), skill.id))
    skill_ids = {skill.id for skill in ranked}
    rows: list[GraspCanaryResult] = []
    for canary in DEFAULT_GRASP_CANARIES:
        if canary.expected_winner not in skill_ids:
            continue
        matches = [
            skill
            for skill in ranked
            if "grasp_profile" in skill.recovery_hints and eval_applies_to(skill.applies_to, canary.state)
        ]
        winner = matches[-1] if matches else None
        rows.append(
            GraspCanaryResult(
                name=canary.name,
                expected_winner=canary.expected_winner,
                expected_profile=canary.expected_profile,
                matched_skill_ids=tuple(skill.id for skill in matches),
                winner_skill_id="" if winner is None else winner.id,
                winner_profile="" if winner is None else str(winner.recovery_hints.get("grasp_profile") or ""),
            )
        )
    return tuple(rows)


def check_grasp_skill_library(
    index_path: str | Path,
    *,
    extra_skill_files: Sequence[str | Path] = (),
) -> GraspStaticReport:
    index = Path(index_path)
    skills_root = index.parent
    data = load_index(index)
    grasp_profile_registry = load_grasp_profile_registry(index_path=index)
    online_rels = {str(item).replace("\\", "/") for item in data.get("online") or []}
    findings: list[GraspStaticFinding] = []

    _check_catalog(skills_root, online_rels, findings)

    try:
        all_online = resolve_online_skills(index)
    except SkillSchemaError as exc:
        _finding(findings, "ERROR", "online_index_schema_error", str(exc), path=str(index))
        all_online = []
    online_grasp_specs = [
        spec for spec in all_online if spec.kind == "recovery_hint" and spec.scope == "grasp"
    ]
    grasp_by_id = {spec.id: spec for spec in online_grasp_specs}
    for extra_path in extra_skill_files:
        try:
            spec = load_skill(extra_path)
        except SkillSchemaError as exc:
            _finding(
                findings,
                "ERROR",
                "extra_grasp_skill_schema_error",
                str(exc),
                path=str(extra_path),
            )
            continue
        if spec.kind != "recovery_hint" or spec.scope != "grasp":
            _finding(
                findings,
                "ERROR",
                "extra_grasp_skill_wrong_kind_or_scope",
                "extra grasp skill must be kind=recovery_hint and scope=grasp",
                skill=spec,
            )
            continue
        grasp_by_id[spec.id] = spec
    grasp_specs = list(grasp_by_id.values())
    profile_summaries: list[GraspProfileSummary] = []
    for spec in grasp_specs:
        if spec.kind != "recovery_hint" or spec.scope != "grasp":
            _finding(
                findings,
                "ERROR",
                "bad_grasp_skill_kind_or_scope",
                "grasp skill must be kind=recovery_hint and scope=grasp",
                skill=spec,
            )
        if spec.trigger or spec.hook or spec.backend:
            _finding(
                findings,
                "ERROR",
                "grasp_skill_declares_trigger_or_backend",
                "grasp skills must not trigger recovery or select a backend",
                skill=spec,
            )
        if spec.recovery_hints.get("target") not in ("target", "", None):
            _finding(
                findings,
                "WARN",
                "grasp_target_not_symbolic_target",
                "grasp skills normally leave the selected target as symbolic target",
                skill=spec,
                detail={"target": spec.recovery_hints.get("target")},
            )
        _check_matching_scope(spec, findings)
        _check_executor_params(spec, findings)
        summary = _check_profile_sampling(spec, findings, registry=grasp_profile_registry)
        if summary is not None:
            profile_summaries.append(summary)

    canaries = _evaluate_canaries(grasp_specs)
    for row in canaries:
        if not row.passed:
            findings.append(
                GraspStaticFinding(
                    severity="ERROR",
                    code="grasp_canary_mismatch",
                    message="grasp canary matched a different winning skill/profile than expected",
                    detail=row.to_dict(),
                )
            )

    _check_shared_profile_consumers(skills_root, findings)

    return GraspStaticReport(
        index_path=str(index),
        online_grasp_skill_ids=tuple(
            spec.id for spec in sorted(online_grasp_specs, key=lambda item: (-item.priority, item.id))
        ),
        checked_grasp_skill_ids=tuple(spec.id for spec in sorted(grasp_specs, key=lambda item: (-item.priority, item.id))),
        profile_summaries=tuple(profile_summaries),
        canary_results=canaries,
        findings=tuple(findings),
    )


def render_grasp_static_markdown(report: GraspStaticReport) -> str:
    lines = [
        "# Grasp Skill Static Gate",
        "",
        f"- Index: `{report.index_path}`",
        f"- Online grasp skills: {len(report.online_grasp_skill_ids)}",
        f"- Checked grasp skills: {len(report.checked_grasp_skill_ids)}",
        f"- Errors: {report.error_count}",
        f"- Warnings: {report.warning_count}",
        "",
        "## Findings",
        "",
    ]
    if not report.findings:
        lines.append("No findings.")
    else:
        lines.extend(["| severity | code | skill | message |", "| --- | --- | --- | --- |"])
        for item in report.findings:
            skill = item.skill_id or item.path or "-"
            lines.append(f"| {item.severity} | `{item.code}` | `{skill}` | {item.message} |")

    lines.extend(["", "## Canary Matches", "", "| canary | expected | winner | matched |", "| --- | --- | --- | --- |"])
    for row in report.canary_results:
        expected = f"{row.expected_winner} / {row.expected_profile}"
        winner = f"{row.winner_skill_id or '-'} / {row.winner_profile or '-'}"
        matched = ";".join(row.matched_skill_ids) if row.matched_skill_ids else "-"
        lines.append(f"| {row.name} | `{expected}` | `{winner}` | `{matched}` |")

    lines.extend(["", "## Profile Sampling", "", "| skill | profile | samples | width_m | modes |", "| --- | --- | ---: | ---: | --- |"])
    for item in report.profile_summaries:
        modes = ";".join(item.sample_modes) if item.sample_modes else "-"
        lines.append(
            f"| `{item.skill_id}` | `{item.profile}` | {item.sample_count} | {item.gripper_width_m:.4f} | `{modes}` |"
        )
    return "\n".join(lines) + "\n"
