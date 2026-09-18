"""Skill YAML/Markdown schema. Triggers are declarative predicates, never Python."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .predicate_registry import BUILTIN_APPLIES_PREDICATES, BUILTIN_TRIGGER_PREDICATES

ALLOWED_KINDS = ("trigger", "repair", "diagnostics", "recovery_hint", "task_binding")
ALLOWED_TRACKS = ("pair", "fail_only")
ALLOWED_HOOKS = (
    "after_pi0_query",
    "after_gripper_close",
    "before_trajectory_step",
    "after_recovery_attempt",
)
ALLOWED_PREDICATES = tuple(sorted(BUILTIN_TRIGGER_PREDICATES))
ALLOWED_APPLIES_PREDICATES = tuple(sorted(BUILTIN_APPLIES_PREDICATES))
ALLOWED_RECOVERY_HINT_KEYS = ("grasp_profile", "target", "params")
FORBIDDEN_TRIGGER_KEYS = {
    "query_idx",
    "query_index",
    "contacts",
    "contact",
    "seed",
    "ee_xyz",
    "target_xyz",
    "absolute_xyz",
}
_QUERY_NUM_RE = re.compile(r"\bquery[_ ]?(?:idx|index|number|#)?\s*[:=]\s*\d+", re.I)
_XYZ_LIST_RE = re.compile(
    r"\[\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\]"
)


class SkillSchemaError(ValueError):
    """Skill file is not admissible."""


@dataclass
class SkillSpec:
    id: str
    name: str
    kind: str
    hook: str | None
    priority: int
    when_to_apply: str
    when_not_to_apply: str
    failure_signature: list[str]
    recovery_point: str
    trigger: dict[str, Any]
    backend: str
    evidence: dict[str, Any]
    recovery_hints: dict[str, Any] = field(default_factory=dict)
    task_binding_profile: str = ""
    scope: str = ""
    applies_to: dict[str, Any] = field(default_factory=dict)
    pending_backend: bool = False
    track: str = "pair"
    body: str = ""
    path: str = ""
    predicate_registry: Any = None

    @property
    def online(self) -> bool:
        if self.kind == "diagnostics" or self.track != "pair" or self.pending_backend:
            return False
        if self.kind == "recovery_hint":
            return bool(self.recovery_hints)
        if self.kind == "task_binding":
            return bool(self.task_binding_profile)
        return bool(self.backend)


def _load_yaml(text: str) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise SkillSchemaError("PyYAML is required to parse skill front matter") from exc
    return yaml.safe_load(text)


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    raw = text.replace("\r\n", "\n")
    if not raw.startswith("---"):
        raise SkillSchemaError("skill file must start with YAML front matter (---)")
    rest = raw[3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end < 0:
        raise SkillSchemaError("unterminated YAML front matter")
    data = _load_yaml(rest[:end])
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise SkillSchemaError("front matter must be a mapping")
    body = rest[end + 4 :].lstrip("\n")
    return data, body


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise SkillSchemaError(f"expected a string list, got {type(value).__name__}")


def normalize_recovery_hints(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise SkillSchemaError("recovery_hints must be a mapping")
    extra = sorted(set(str(key) for key in value) - set(ALLOWED_RECOVERY_HINT_KEYS))
    if extra:
        raise SkillSchemaError(f"unknown recovery_hints keys: {extra}")
    hints: dict[str, Any] = {}
    profile = value.get("grasp_profile")
    if profile not in (None, ""):
        profile_text = str(profile).strip()
        if profile_text:
            hints["grasp_profile"] = profile_text
    target = value.get("target")
    if target not in (None, ""):
        hints["target"] = str(target)
    params = value.get("params")
    if params not in (None, ""):
        if not isinstance(params, Mapping):
            raise SkillSchemaError("recovery_hints.params must be a mapping")
        hints["params"] = dict(params)
    return hints


def normalize_predicates(node: Any) -> list[tuple[str, Any]]:
    if node is None:
        return []
    items: list[tuple[str, Any]] = []
    if isinstance(node, Mapping):
        items.extend(node.items())
    elif isinstance(node, list):
        for entry in node:
            if not isinstance(entry, Mapping) or not entry:
                raise SkillSchemaError("each trigger clause must be a one-key mapping")
            items.extend(entry.items())
    else:
        raise SkillSchemaError("trigger all/any must be a list or mapping")
    return [(str(key), value) for key, value in items]


def iter_trigger_predicates(trigger: Mapping[str, Any] | None) -> Iterable[tuple[str, Any]]:
    trigger = dict(trigger or {})
    for group in ("all", "any"):
        yield from normalize_predicates(trigger.get(group))


def _walk_keys(node: Any) -> Iterable[str]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            yield str(key)
            yield from _walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_keys(item)


def _predicate_registry_or_default(predicate_registry: Any = None) -> Any:
    if predicate_registry is not None:
        return predicate_registry
    from .predicate_registry import PredicateRegistry

    return PredicateRegistry.builtins()


def trigger_schema_errors(trigger: Mapping[str, Any] | None, *, predicate_registry: Any = None) -> list[str]:
    errors: list[str] = []
    registry = _predicate_registry_or_default(predicate_registry)
    trigger = dict(trigger or {})
    extra_groups = set(trigger) - {"all", "any"}
    if extra_groups:
        errors.append(f"unknown trigger groups: {sorted(extra_groups)}")
    dumped = str(trigger)
    if _QUERY_NUM_RE.search(dumped):
        errors.append("trigger must not hard-code a query index")
    if _XYZ_LIST_RE.search(dumped):
        errors.append("trigger must not hard-code absolute xyz coordinates")
    for key in _walk_keys(trigger):
        if key in FORBIDDEN_TRIGGER_KEYS:
            errors.append(f"forbidden trigger key: {key}")
    for name, _value in iter_trigger_predicates(trigger):
        if not registry.is_trigger_predicate_allowed(name):
            errors.append(f"unknown predicate: {name}")
    return errors


def applies_to_schema_errors(applies_to: Mapping[str, Any] | None, *, predicate_registry: Any = None) -> list[str]:
    errors: list[str] = []
    registry = _predicate_registry_or_default(predicate_registry)
    applies_to = dict(applies_to or {})
    extra_groups = set(applies_to) - {"all", "any"}
    if extra_groups:
        errors.append(f"unknown applies_to groups: {sorted(extra_groups)}")
    dumped = str(applies_to)
    if _QUERY_NUM_RE.search(dumped):
        errors.append("applies_to must not hard-code a query index")
    if _XYZ_LIST_RE.search(dumped):
        errors.append("applies_to must not hard-code absolute xyz coordinates")
    for key in _walk_keys(applies_to):
        if key in FORBIDDEN_TRIGGER_KEYS:
            errors.append(f"forbidden applies_to key: {key}")
    for name, _value in iter_trigger_predicates(applies_to):
        if not registry.is_applies_predicate_allowed(name):
            errors.append(f"unknown applies_to predicate: {name}")
    return errors


def validate_skill(spec: SkillSpec, *, predicate_registry: Any = None) -> list[str]:
    errors: list[str] = []
    registry = _predicate_registry_or_default(predicate_registry or spec.predicate_registry)
    if not spec.id:
        errors.append("missing id")
    if spec.kind not in ALLOWED_KINDS:
        errors.append(f"kind must be one of {ALLOWED_KINDS}")
    if spec.kind == "diagnostics":
        return errors
    if spec.track not in ALLOWED_TRACKS:
        errors.append(f"track must be one of {ALLOWED_TRACKS}")
    if spec.kind == "recovery_hint":
        if spec.hook not in (None, ""):
            errors.append("recovery_hint must not declare hook")
        if spec.backend:
            errors.append("recovery_hint must not declare backend")
        if spec.trigger:
            errors.append("recovery_hint must use applies_to, not trigger")
        if not spec.recovery_hints:
            errors.append("recovery_hint requires recovery_hints")
        errors.extend(applies_to_schema_errors(spec.applies_to, predicate_registry=registry))
        return errors
    if spec.kind == "task_binding":
        if spec.scope != "task_binding":
            errors.append("task_binding skill requires scope: task_binding")
        if spec.hook not in (None, ""):
            errors.append("task_binding must not declare hook")
        if spec.backend:
            errors.append("task_binding must not declare backend")
        if spec.trigger:
            errors.append("task_binding must use applies_to, not trigger")
        if spec.recovery_hints:
            errors.append("task_binding must not declare recovery_hints")
        if not spec.task_binding_profile:
            errors.append("task_binding requires task_binding_profile")
        if not spec.applies_to:
            errors.append("task_binding requires applies_to")
        dumped = str(spec.applies_to).lower()
        if "bddl" in dumped:
            errors.append("task_binding applies_to must not reference BDDL fields")
        if _XYZ_LIST_RE.search(dumped) or any(key in dumped for key in ("absolute_xyz", "target_xyz", "goal_xyz")):
            errors.append("task_binding applies_to must not hard-code coordinates")
        if re.search(r"\b[a-z][a-z0-9_]*_\d+(?:_main)?\b", dumped):
            errors.append("task_binding applies_to must not hard-code a concrete instance")
        errors.extend(applies_to_schema_errors(spec.applies_to, predicate_registry=registry))
        return errors
    if spec.hook not in ALLOWED_HOOKS:
        errors.append(f"hook must be one of {ALLOWED_HOOKS}")
    if not spec.backend and not spec.pending_backend:
        errors.append("backend is required unless pending_backend is true")
    errors.extend(trigger_schema_errors(spec.trigger, predicate_registry=registry))
    if spec.applies_to:
        errors.extend(applies_to_schema_errors(spec.applies_to, predicate_registry=registry))
    return errors


def infer_track(data: Mapping[str, Any], path: str = "") -> str:
    raw = data.get("track")
    if raw not in (None, ""):
        return str(raw)
    normalized = str(path).replace("\\", "/")
    if "/fail_only/" in normalized:
        return "fail_only"
    return "pair"


def spec_from_mapping(
    data: Mapping[str, Any],
    body: str = "",
    path: str = "",
    *,
    predicate_registry: Any = None,
) -> SkillSpec:
    evidence = data.get("evidence") or {}
    if not isinstance(evidence, Mapping):
        raise SkillSchemaError("evidence must be a mapping")
    spec = SkillSpec(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or data.get("id") or ""),
        kind=str(data.get("kind") or ""),
        hook=None if data.get("hook") in (None, "") else str(data.get("hook")),
        priority=int(data.get("priority") or 0),
        when_to_apply=str(data.get("when_to_apply") or ""),
        when_not_to_apply=str(data.get("when_not_to_apply") or ""),
        failure_signature=_as_str_list(data.get("failure_signature")),
        recovery_point=str(data.get("recovery_point") or ""),
        trigger=dict(data.get("trigger") or {}),
        backend=str(data.get("backend") or ""),
        evidence={
            "tasks": _as_str_list(evidence.get("tasks")),
            "episodes": _as_str_list(evidence.get("episodes")),
        },
        recovery_hints=normalize_recovery_hints(data.get("recovery_hints")),
        task_binding_profile=str(
            data.get("task_binding_profile")
            or ((data.get("binding") or {}).get("profile") if isinstance(data.get("binding"), Mapping) else "")
            or ""
        ).strip(),
        scope=str(data.get("scope") or ""),
        applies_to=dict(data.get("applies_to") or {}),
        pending_backend=bool(data.get("pending_backend", False)),
        track=infer_track(data, path),
        body=body,
        path=path,
        predicate_registry=predicate_registry,
    )
    errors = validate_skill(spec, predicate_registry=predicate_registry)
    if errors:
        raise SkillSchemaError("; ".join(errors))
    return spec


def parse_skill_markdown(text: str, path: str = "", *, predicate_registry: Any = None) -> SkillSpec:
    data, body = parse_front_matter(text)
    return spec_from_mapping(data, body=body, path=path, predicate_registry=predicate_registry)


def load_skill(path: str | Path, *, predicate_registry: Any = None) -> SkillSpec:
    skill_path = Path(path)
    return parse_skill_markdown(
        skill_path.read_text(encoding="utf-8"),
        path=str(skill_path),
        predicate_registry=predicate_registry,
    )


def load_index(index_path: str | Path) -> dict[str, Any]:
    path = Path(index_path)
    data = _load_yaml(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SkillSchemaError("skills/_index.yaml must be a mapping")
    return data


def _predicate_registry_for_index(index_path: str | Path, predicate_registry: Any = None) -> Any:
    if predicate_registry is not None:
        return predicate_registry
    from .predicate_registry import load_predicate_registry

    return load_predicate_registry(index_path=index_path)


def resolve_online_skills(index_path: str | Path, *, predicate_registry: Any = None) -> list[SkillSpec]:
    path = Path(index_path)
    root = path.parent
    data = load_index(path)
    registry = _predicate_registry_for_index(path, predicate_registry)
    specs: list[SkillSpec] = []
    for rel in data.get("online") or []:
        spec = load_skill(root / str(rel), predicate_registry=registry)
        if spec.kind == "task_binding":
            raise SkillSchemaError(f"task_binding skill must use the task_binding index section: {rel}")
        if spec.kind == "diagnostics":
            raise SkillSchemaError(f"diagnostics skill cannot be online: {rel}")
        if spec.track == "fail_only":
            raise SkillSchemaError(f"fail_only skill cannot be online: {rel}")
        if spec.pending_backend:
            raise SkillSchemaError(f"pending backend cannot be online: {rel}")
        specs.append(spec)
    specs.sort(key=lambda item: (-int(item.priority), item.id))
    return specs


def resolve_mining_skills(index_path: str | Path, *, predicate_registry: Any = None) -> list[SkillSpec]:
    """Load pair + fail_only drafts for offline mining. Never used by `--enable_skills`."""
    path = Path(index_path)
    root = path.parent
    data = load_index(path)
    registry = _predicate_registry_for_index(path, predicate_registry)
    specs: list[SkillSpec] = []
    seen: set[str] = set()
    indexed = [str(rel) for rel in list(data.get("fail_only") or []) + list(data.get("online") or [])]
    for rel in indexed:
        spec = load_skill(root / rel, predicate_registry=registry)
        if spec.kind in {"diagnostics", "task_binding"} or spec.id in seen:
            continue
        seen.add(spec.id)
        specs.append(spec)
    for folder in ("pair", "fail_only"):
        folder_path = root / folder
        if not folder_path.is_dir():
            continue
        for md in sorted(folder_path.rglob("*.md")):
            spec = load_skill(md, predicate_registry=registry)
            if spec.kind in {"diagnostics", "task_binding"} or spec.id in seen:
                continue
            seen.add(spec.id)
            specs.append(spec)
    specs.sort(key=lambda item: (-int(item.priority), item.id))
    return specs


def resolve_task_binding_skills(
    index_path: str | Path,
    *,
    mining: bool = False,
    predicate_registry: Any = None,
) -> list[SkillSpec]:
    """Load the isolated static task-binding lane from a skill-pack index."""

    path = Path(index_path)
    root = path.parent
    data = load_index(path)
    registry = _predicate_registry_for_index(path, predicate_registry)
    entries = [(str(rel), "pair") for rel in data.get("task_binding") or []]
    if mining:
        entries += [(str(rel), "fail_only") for rel in data.get("task_binding_fail_only") or []]
    specs: list[SkillSpec] = []
    seen: set[str] = set()
    for rel, expected_track in entries:
        spec = load_skill(root / rel, predicate_registry=registry)
        if spec.kind != "task_binding":
            raise SkillSchemaError(f"task_binding index entry has kind {spec.kind!r}: {rel}")
        if spec.track != expected_track:
            raise SkillSchemaError(
                f"task_binding index section requires track {expected_track!r}, got {spec.track!r}: {rel}"
            )
        if not mining and spec.track != "pair":
            raise SkillSchemaError(f"fail_only task_binding skill cannot be online: {rel}")
        if spec.id in seen:
            raise SkillSchemaError(f"duplicate task_binding skill id: {spec.id}")
        seen.add(spec.id)
        specs.append(spec)
    specs.sort(key=lambda item: (-int(item.priority), item.id))
    return specs
