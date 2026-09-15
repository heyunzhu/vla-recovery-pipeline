"""Draft/shadow diagnostic signals for repair skill authoring."""

from .registry import (
    DiagnosticRegistry,
    DiagnosticRegistryError,
    DiagnosticSignalSpec,
    default_registry_path,
    load_registry,
)
from .runtime import DiagnosticSignalRuntime, parse_active_statuses

__all__ = [
    "DiagnosticRegistry",
    "DiagnosticRegistryError",
    "DiagnosticSignalRuntime",
    "DiagnosticSignalSpec",
    "default_registry_path",
    "load_registry",
    "parse_active_statuses",
]
