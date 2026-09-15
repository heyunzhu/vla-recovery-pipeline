"""Runtime for shadow diagnostic signal providers."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections import defaultdict, deque
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .registry import DIAGNOSTIC_STATUSES, DiagnosticRegistry, DiagnosticSignalSpec

ProviderFn = Callable[[Mapping[str, Any], tuple[Mapping[str, Any], ...]], Mapping[str, Any]]


def parse_active_statuses(value: str | None) -> set[str]:
    if value is None:
        return set()
    statuses = {item.strip() for item in str(value).split(",") if item.strip()}
    unknown = sorted(statuses - set(DIAGNOSTIC_STATUSES))
    if unknown:
        raise ValueError(f"unknown diagnostic signal statuses: {unknown}")
    return statuses


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def _load_provider(path: str) -> ProviderFn:
    file_path = Path(path)
    if file_path.exists() and file_path.suffix == ".py":
        module_name = f"_libero_diagnostic_provider_{abs(hash(str(file_path.resolve())))}"
        spec = importlib.util.spec_from_file_location(module_name, file_path.resolve())
        if spec is None or spec.loader is None:
            raise TypeError(f"cannot load diagnostic provider file {path!r}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        fn = getattr(module, "compute", None)
        if not callable(fn):
            raise TypeError(f"diagnostic provider {path!r} must expose compute(state, history)")
        return fn
    module = importlib.import_module(path)
    fn = getattr(module, "compute", None)
    if not callable(fn):
        raise TypeError(f"diagnostic provider {path!r} must expose compute(state, history)")
    return fn


class DiagnosticSignalRuntime:
    def __init__(
        self,
        registry: DiagnosticRegistry,
        *,
        active_statuses: set[str] | None = None,
        history_size: int = 32,
    ) -> None:
        self.registry = registry
        self.active_statuses = set(active_statuses or set())
        self.history_size = int(history_size)
        self._providers: dict[str, ProviderFn] = {}
        self._history: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=self.history_size))

    @classmethod
    def from_registry(
        cls,
        registry: DiagnosticRegistry,
        *,
        active_statuses: set[str] | None = None,
        history_size: int = 32,
    ) -> "DiagnosticSignalRuntime":
        return cls(registry, active_statuses=active_statuses, history_size=history_size)

    @property
    def active_specs(self) -> tuple[DiagnosticSignalSpec, ...]:
        return self.registry.for_statuses(self.active_statuses)

    def _provider(self, spec: DiagnosticSignalSpec) -> ProviderFn:
        if spec.id not in self._providers:
            self._providers[spec.id] = _load_provider(spec.provider)
        return self._providers[spec.id]

    def compute(self, hook: str, state: Mapping[str, Any]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        values: dict[str, Any] = {}
        errors: list[str] = []
        state_snapshot = dict(state)
        for spec in self.active_specs:
            if spec.hook != hook:
                continue
            outputs: dict[str, Any] = {}
            error = ""
            missing_outputs: list[str] = []
            unexpected_outputs: list[str] = []
            missing_inputs = [name for name in spec.inputs if name not in state_snapshot]
            try:
                raw = self._provider(spec)(MappingProxyType(dict(state_snapshot)), tuple(self._history[spec.id]))
                if not isinstance(raw, Mapping):
                    raise TypeError(f"provider returned {type(raw).__name__}, expected mapping")
                allowed = set(spec.outputs)
                unexpected_outputs = sorted(str(key) for key in raw if str(key) not in allowed)
                outputs = {
                    name: _jsonable(raw.get(name))
                    for name in spec.outputs
                    if name in raw
                }
                missing_outputs = [name for name in spec.outputs if name not in outputs]
                if unexpected_outputs:
                    error = f"unexpected provider outputs: {unexpected_outputs}"
                    errors.append(f"{spec.id}: {error}")
                values.update(outputs)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                errors.append(f"{spec.id}: {error}")
            row = {
                "id": spec.id,
                "status": spec.status,
                "hook": spec.hook,
                "provider": spec.provider,
                "outputs": outputs,
                "missing_inputs": missing_inputs,
                "missing_outputs": missing_outputs,
                "unexpected_outputs": unexpected_outputs,
                "error": error,
            }
            results.append(row)
            self._history[spec.id].append(
                {
                    "hook": hook,
                    "inputs": {name: _jsonable(state_snapshot.get(name)) for name in spec.inputs},
                    "outputs": dict(outputs),
                    "error": error,
                }
            )
        return {
            "hook": hook,
            "active_statuses": sorted(self.active_statuses),
            "results": results,
            "values": values,
            "errors": errors,
        }
