"""Registry for draft/shadow diagnostic signal providers.

Diagnostic signals are shared qstate producers. They are versioned and
validated separately from repair skills so an agent can propose them without
quietly changing online trigger behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from experiments.robot.libero.skill_pipeline.trace_schema import QUERY_TRACE_FIELDS

DIAGNOSTIC_STATUSES = ("draft", "shadow", "online", "retired")
DIAGNOSTIC_HOOKS = ("after_pi0_query",)
PROVIDER_PREFIX = "experiments.robot.libero.skill_pipeline.diagnostics.providers."
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_OUTPUT_RE = re.compile(r"^diag_[a-z][a-z0-9_]*$")
_TRACE_FIELD_SET = set(QUERY_TRACE_FIELDS)


class DiagnosticRegistryError(ValueError):
    """Diagnostic signal registry is not admissible."""


@dataclass(frozen=True)
class DiagnosticSignalSpec:
    id: str
    status: str
    hook: str
    provider: str
    inputs: tuple[str, ...] = field(default_factory=tuple)
    outputs: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""
    online_safe: bool = False
    uses_future_rollout: bool = False
    uses_oracle_success: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DiagnosticSignalSpec":
        if not isinstance(data, Mapping):
            raise DiagnosticRegistryError("each diagnostic signal must be a mapping")
        payload = dict(data)
        known = {
            "id",
            "status",
            "hook",
            "provider",
            "inputs",
            "outputs",
            "description",
            "online_safe",
            "uses_future_rollout",
            "uses_oracle_success",
            "metadata",
        }
        extra = sorted(set(payload) - known)
        if extra:
            raise DiagnosticRegistryError(f"unknown diagnostic signal keys for {payload.get('id')}: {extra}")
        spec = cls(
            id=str(payload.get("id") or ""),
            status=str(payload.get("status") or "draft"),
            hook=str(payload.get("hook") or "after_pi0_query"),
            provider=str(payload.get("provider") or ""),
            inputs=tuple(str(item) for item in (payload.get("inputs") or [])),
            outputs=tuple(str(item) for item in (payload.get("outputs") or [])),
            description=str(payload.get("description") or ""),
            online_safe=bool(payload.get("online_safe", False)),
            uses_future_rollout=bool(payload.get("uses_future_rollout", False)),
            uses_oracle_success=bool(payload.get("uses_oracle_success", False)),
            metadata=dict(payload.get("metadata") or {}),
        )
        return spec


@dataclass(frozen=True)
class DiagnosticRegistry:
    signals: tuple[DiagnosticSignalSpec, ...]
    source_path: Path | None = None

    def for_statuses(self, statuses: set[str]) -> tuple[DiagnosticSignalSpec, ...]:
        return tuple(spec for spec in self.signals if spec.status in statuses and spec.status != "retired")


def default_registry_path() -> Path:
    return Path(__file__).resolve().parent / "registry.yaml"


def _is_abs(path: Path) -> bool:
    return path.is_absolute() or bool(path.drive)


def _under(path: Path, roots: Sequence[Path]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _looks_like_file_provider(provider: str) -> bool:
    text = str(provider or "")
    return text.endswith(".py") or "/" in text or "\\" in text


def _normalize_provider(
    provider: str,
    *,
    source: Path,
    provider_roots: Sequence[str | Path] = (),
) -> str:
    text = str(provider or "").strip()
    if not text or text.startswith(PROVIDER_PREFIX):
        return text
    if not _looks_like_file_provider(text):
        return text
    raw = Path(text)
    roots = [Path(root) for root in provider_roots if str(root)]
    roots.extend([source.parent, source.parent.parent])
    candidates = [raw] if _is_abs(raw) else [root / raw for root in roots]
    for candidate in candidates:
        if candidate.exists() and candidate.suffix == ".py":
            resolved = candidate.resolve()
            if not _under(resolved, roots):
                raise DiagnosticRegistryError(
                    f"diagnostic provider path must stay under the active pack/registry roots: {resolved}"
                )
            return str(resolved)
    raise DiagnosticRegistryError(f"diagnostic provider file does not exist: {text}")


def validate_signal_spec(
    spec: DiagnosticSignalSpec,
    *,
    provider_roots: Sequence[str | Path] = (),
) -> None:
    if not _ID_RE.match(spec.id):
        raise DiagnosticRegistryError(f"invalid diagnostic signal id: {spec.id!r}")
    if spec.status not in DIAGNOSTIC_STATUSES:
        raise DiagnosticRegistryError(f"{spec.id}: status must be one of {DIAGNOSTIC_STATUSES}")
    if spec.hook not in DIAGNOSTIC_HOOKS:
        raise DiagnosticRegistryError(f"{spec.id}: hook must be one of {DIAGNOSTIC_HOOKS}")
    if spec.status != "retired" and not spec.provider:
        raise DiagnosticRegistryError(f"{spec.id}: non-retired diagnostic signal requires provider")
    provider_path_ok = False
    if spec.provider and _looks_like_file_provider(spec.provider):
        resolved = Path(spec.provider)
        roots = [Path(root) for root in provider_roots if str(root)]
        provider_path_ok = resolved.exists() and resolved.suffix == ".py" and _under(resolved, roots)
    if spec.provider and not spec.provider.startswith(PROVIDER_PREFIX) and not provider_path_ok:
        raise DiagnosticRegistryError(
            f"{spec.id}: provider must live under {PROVIDER_PREFIX!r} or an active pack root, got {spec.provider!r}"
        )
    if not spec.outputs and spec.status != "retired":
        raise DiagnosticRegistryError(f"{spec.id}: non-retired diagnostic signal requires outputs")
    for output in spec.outputs:
        if not _OUTPUT_RE.match(output):
            raise DiagnosticRegistryError(f"{spec.id}: output must start with diag_ and be snake_case: {output!r}")
        if output in _TRACE_FIELD_SET:
            raise DiagnosticRegistryError(f"{spec.id}: output collides with query trace field: {output}")
    forbidden_inputs = {"success", "done", "episode_success", "future_rollout", "contacts"}
    bad_inputs = sorted(forbidden_inputs.intersection(spec.inputs))
    if bad_inputs:
        raise DiagnosticRegistryError(f"{spec.id}: forbidden diagnostic inputs: {bad_inputs}")
    if spec.uses_future_rollout:
        raise DiagnosticRegistryError(f"{spec.id}: online diagnostic signals must not use future rollout results")
    if spec.uses_oracle_success:
        raise DiagnosticRegistryError(f"{spec.id}: diagnostic signals must not use oracle success labels")
    if spec.status == "online" and not spec.online_safe:
        raise DiagnosticRegistryError(f"{spec.id}: online status requires online_safe=true")


def load_registry(
    path: str | Path | None = None,
    *,
    provider_roots: Sequence[str | Path] = (),
) -> DiagnosticRegistry:
    source = Path(path) if path else default_registry_path()
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise DiagnosticRegistryError("diagnostic registry root must be a mapping")
    signals_raw = payload.get("signals") or []
    if not isinstance(signals_raw, list):
        raise DiagnosticRegistryError("diagnostic registry `signals` must be a list")
    roots = [Path(root) for root in provider_roots if str(root)]
    roots.extend([source.parent, source.parent.parent])
    signals_list: list[DiagnosticSignalSpec] = []
    for item in signals_raw:
        spec = DiagnosticSignalSpec.from_mapping(item)
        spec = replace(
            spec,
            provider=_normalize_provider(spec.provider, source=source, provider_roots=roots),
        )
        validate_signal_spec(spec, provider_roots=roots)
        signals_list.append(spec)
    signals = tuple(signals_list)
    seen: set[str] = set()
    for spec in signals:
        if spec.id in seen:
            raise DiagnosticRegistryError(f"duplicate diagnostic signal id: {spec.id}")
        seen.add(spec.id)
    return DiagnosticRegistry(signals=signals, source_path=source)
