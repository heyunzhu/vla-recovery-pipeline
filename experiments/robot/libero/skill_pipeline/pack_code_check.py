"""Cheap pre-GPU checks for pack-authored code.

The offline scan and same-init validation only exercise the branches an episode
happens to reach. This module calls every channel the pack declares once, through
the real registries and the pack's own profile catalogs, so a wrong protocol, a
non-deterministic sampler, a missing catalog entry, or a file/network side effect
is reported before a GPU run is spent on it.

Two deliberate limits:

* Only the *declared* ids are probed. A branch that no id reaches stays untested.
* Imports of engine modules are not forbidden here; the offline adapter style
  guidance in the actor prompt covers that, and real packs legitimately import
  small engine helpers such as frame conversions. What is forbidden is code with
  side effects or non-determinism, because the offline scan has to replay it.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .adapter_discovery import declares_ids
from .schema import SkillSchemaError

CHANNEL_BY_FILENAME: dict[str, str] = {
    "grasp_profiles.py": "grasp_profile",
    "grounding_profiles.py": "grounding_hint",
    "geometry_profiles.py": "geometry_hint",
    "place_policies.py": "place_policy",
    "predicates.py": "predicate",
}

REQUIRED_SYMBOLS: dict[str, tuple[str, ...]] = {
    "grasp_profile": ("sample_grasp_profile", "profile_gripper_width"),
    "grounding_hint": ("normalize_grounding_profile_params",),
    "geometry_hint": ("normalize_geometry_profile_params",),
    "place_policy": (),
    "predicate": (),
}

PLACE_HOOK_SYMBOLS = ("resolve_hover_policy", "resolve_align_policy", "resolve_release_policy")
ID_SYMBOLS: dict[str, tuple[str, ...]] = {
    "grasp_profile": ("PROFILE_IDS",),
    "grounding_hint": ("PROFILE_IDS",),
    "geometry_hint": ("PROFILE_IDS",),
    "place_policy": ("PROFILE_IDS",),
    "predicate": ("PREDICATE_IDS", "APPLIES_PREDICATE_IDS"),
}

# Files that ship a profile catalog the code must stay in sync with.
CATALOG_FILENAME: dict[str, str] = {
    "grounding_hint": "grounding.yaml",
    "geometry_hint": "geometry.yaml",
    "place_policy": "place.yaml",
}

FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "ctypes",
        "datetime",
        "ftplib",
        "http",
        "importlib",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "random",
        "requests",
        "secrets",
        "shutil",
        "socket",
        "subprocess",
        "sys",
        "tempfile",
        "threading",
        "time",
        "urllib",
        "uuid",
    }
)
FORBIDDEN_CALLS = frozenset({"open", "eval", "exec", "compile", "__import__", "input", "breakpoint"})
FORBIDDEN_ATTRIBUTE_PREFIXES = ("random.", "np.random.", "numpy.random.", "time.time", "datetime.")
SYNTHETIC_DIMS = (0.06, 0.06, 0.06)


@dataclass
class PackCodeFileReport:
    path: str
    channel: str
    ok: bool = True
    declared_ids: list[str] = field(default_factory=list)
    checked_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "channel": self.channel,
            "ok": self.ok,
            "declared_ids": list(self.declared_ids),
            "checked_ids": list(self.checked_ids),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _attribute_chain(node: ast.AST) -> str:
    parts: list[str] = []
    current: Any = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attribute_chain(node)
    return ""


def ast_issues(source: str) -> tuple[list[str], list[str]]:
    """Report imports/calls that make pack code non-replayable."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"cannot parse: {exc}"], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = str(alias.name).split(".")[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    errors.append(f"forbidden import for replayable pack code: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            root = module.split(".")[0]
            if node.level == 0 and root in FORBIDDEN_IMPORT_ROOTS:
                errors.append(f"forbidden import for replayable pack code: {module}")
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in FORBIDDEN_CALLS:
                errors.append(f"forbidden call in replayable pack code: {name}")
        elif isinstance(node, ast.Attribute):
            chain = _attribute_chain(node)
            if any(chain.startswith(prefix) for prefix in FORBIDDEN_ATTRIBUTE_PREFIXES):
                errors.append(f"non-deterministic or environment-dependent attribute: {chain}")
    return sorted(set(errors)), sorted(set(warnings))


def _declared_ids(module: Any, channel: str) -> list[str]:
    out: list[str] = []
    for symbol in ID_SYMBOLS[channel]:
        for item in getattr(module, symbol, ()) or ():
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
    return out


def _probe_place_hooks(module: Any, profile_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for symbol in PLACE_HOOK_SYMBOLS:
        fn = getattr(module, symbol, None)
        if not callable(fn):
            continue
        out[symbol] = fn(profile_id, {}, {"place_profile": profile_id})
    return out


def _check_deterministic(call, label: str, report: PackCodeFileReport, *, repeat: bool = True) -> Any:
    first = call()
    if repeat:
        second = call()
        if repr(first) != repr(second):
            report.fail(f"{label} is not deterministic: two identical calls returned different values")
    return first


def _check_return_mapping(value: Any, label: str, report: PackCodeFileReport) -> None:
    if value is not None and not isinstance(value, Mapping):
        report.fail(f"{label} must return a mapping or None, got {type(value).__name__}")


def _check_grasp(report: PackCodeFileReport, pack_root: Path, ids: Sequence[str]) -> None:
    from experiments.robot.libero.tiptop_repro.grasp_profiles import (
        load_grasp_profile_registry,
        profile_gripper_width,
        sample_grasp_profile,
    )

    index_path = pack_root / "skills" / "_index.yaml"
    registry = load_grasp_profile_registry(index_path=index_path)
    for profile_id in ids:
        if profile_id not in registry.profile_ids:
            report.fail(f"grasp profile is not visible to the engine registry: {profile_id}")
            continue
        report.checked_ids.append(profile_id)
        try:
            samples = _check_deterministic(
                lambda pid=profile_id: sample_grasp_profile(pid, SYNTHETIC_DIMS, rim=False, registry=registry),
                f"sample_grasp_profile({profile_id})",
                report,
            )
        except Exception as exc:  # noqa: BLE001
            report.fail(f"sample_grasp_profile({profile_id}) raised {type(exc).__name__}: {exc}")
            continue
        if not isinstance(samples, list):
            report.fail(f"sample_grasp_profile({profile_id}) must return a list")
        elif not samples:
            report.warnings.append(
                f"sample_grasp_profile({profile_id}) returned no candidate for a 6cm object; check that this is intended"
            )
        try:
            width = _check_deterministic(
                lambda pid=profile_id: profile_gripper_width(pid, SYNTHETIC_DIMS, registry=registry),
                f"profile_gripper_width({profile_id})",
                report,
            )
        except Exception as exc:  # noqa: BLE001
            report.fail(
                f"profile_gripper_width({profile_id}) raised {type(exc).__name__}: {exc}; "
                "the engine requires a numeric aperture"
            )
            continue
        if isinstance(width, bool) or not isinstance(width, (int, float)):
            report.fail(f"profile_gripper_width({profile_id}) must return a number, got {type(width).__name__}")
        elif not 0.0 < float(width) < 0.12:
            report.warnings.append(f"profile_gripper_width({profile_id}) = {float(width):.4f} m looks outside a Panda aperture")


def _check_named_profile(report: PackCodeFileReport, pack_root: Path, channel: str, ids: Sequence[str]) -> None:
    index_path = pack_root / "skills" / "_index.yaml"
    if channel == "grounding_hint":
        from .grounding_profiles import load_grounding_profile_registry as load_registry

        params_key = "grounding_profile"
    elif channel == "geometry_hint":
        from .geometry_profiles import load_geometry_profile_registry as load_registry

        params_key = "geometry_profile"
    else:
        from .place_profiles import load_place_profile_registry as load_registry

        params_key = "place_profile"
    registry = load_registry(index_path=index_path)
    catalog = CATALOG_FILENAME[channel]
    for profile_id in ids:
        if profile_id not in registry.profiles:
            report.fail(
                f"{profile_id} is declared in code but missing from profiles/{catalog}; "
                f"the runtime rejects unknown {params_key} values"
            )
            continue
        report.checked_ids.append(profile_id)
        try:
            hints = _check_deterministic(
                lambda pid=profile_id: registry.expand_recovery_hints({"params": {params_key: pid}}),
                f"expand_recovery_hints({profile_id})",
                report,
            )
        except Exception as exc:  # noqa: BLE001
            report.fail(f"expanding {profile_id} raised {type(exc).__name__}: {exc}")
            continue
        if not isinstance(hints, Mapping):
            report.fail(f"expanding {profile_id} must produce a mapping")


def _check_place(report: PackCodeFileReport, module: Any, ids: Sequence[str]) -> None:
    for profile_id in ids:
        report.checked_ids.append(profile_id)
        try:
            hooks = _check_deterministic(
                lambda pid=profile_id: _probe_place_hooks(module, pid),
                f"place hooks for {profile_id}",
                report,
            )
        except Exception as exc:  # noqa: BLE001
            report.fail(f"place hook for {profile_id} raised {type(exc).__name__}: {exc}")
            continue
        for symbol, value in hooks.items():
            _check_return_mapping(value, f"{symbol}({profile_id})", report)


def _check_predicate(report: PackCodeFileReport, module: Any, ids: Sequence[str]) -> None:
    import copy

    trigger_ids = [str(item).strip() for item in getattr(module, "PREDICATE_IDS", ()) or () if str(item).strip()]
    applies_ids = [str(item).strip() for item in getattr(module, "APPLIES_PREDICATE_IDS", ()) or () if str(item).strip()]
    for predicate_id in ids:
        report.checked_ids.append(predicate_id)
        for symbol, id_set in (("evaluate_predicate", trigger_ids), ("evaluate_applies_predicate", applies_ids)):
            if predicate_id not in id_set:
                continue
            fn = getattr(module, symbol, None)
            if not callable(fn):
                report.fail(f"{predicate_id} is declared for {symbol} but {symbol} is not callable")
                continue
            try:
                result = _check_deterministic(
                    lambda f=fn, pid=predicate_id: f(pid, True, copy.deepcopy({})),
                    f"{symbol}({predicate_id})",
                    report,
                )
            except Exception as exc:  # noqa: BLE001
                report.fail(
                    f"{symbol}({predicate_id}) raised {type(exc).__name__} on an empty state: {exc}; "
                    "predicates must not require keys the runner may not have"
                )
                continue
            if not isinstance(result, bool):
                report.fail(f"{symbol}({predicate_id}) must return a bool, got {type(result).__name__}")


def _load_module(path: Path) -> Any:
    import importlib.util

    module_name = f"_libero_pack_code_check_{abs(hash(str(path.resolve())))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SkillSchemaError(f"cannot load pack code: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def check_pack_code_file(
    path: str | Path,
    *,
    pack_root: str | Path | None = None,
    channel: str | None = None,
) -> PackCodeFileReport:
    """Run every check that does not need a GPU on one pack code file."""
    file_path = Path(path)
    resolved_pack = Path(pack_root) if pack_root else file_path.parent.parent
    channel = channel or CHANNEL_BY_FILENAME.get(file_path.name, "")
    report = PackCodeFileReport(path=str(file_path), channel=channel or "unknown")
    if not channel:
        report.warnings.append(f"not a known pack code channel, skipped: {file_path.name}")
        return report
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        report.fail(f"cannot read: {exc}")
        return report

    ast_errors, ast_warnings = ast_issues(source)
    report.errors.extend(ast_errors)
    report.warnings.extend(ast_warnings)
    if ast_errors:
        report.ok = False
        return report

    if not declares_ids(source, ID_SYMBOLS[channel]):
        report.warnings.append(
            "declares no non-empty " + "/".join(ID_SYMBOLS[channel]) + "; an unfilled scaffold is ignored at load time"
        )
        return report

    try:
        module = _load_module(file_path)
    except Exception as exc:  # noqa: BLE001
        report.fail(f"cannot import: {type(exc).__name__}: {exc}")
        return report

    for symbol in REQUIRED_SYMBOLS[channel]:
        if not callable(getattr(module, symbol, None)):
            report.fail(f"missing callable {symbol}")
    if channel == "place_policy" and not any(callable(getattr(module, name, None)) for name in PLACE_HOOK_SYMBOLS):
        report.fail("exposes none of " + ", ".join(PLACE_HOOK_SYMBOLS))
    if report.errors:
        report.ok = False
        return report

    ids = _declared_ids(module, channel)
    report.declared_ids = list(ids)
    if not ids:
        report.warnings.append("no ids collected from " + "/".join(ID_SYMBOLS[channel]))
        return report

    try:
        if channel == "grasp_profile":
            _check_grasp(report, resolved_pack, ids)
        elif channel in {"grounding_hint", "geometry_hint"}:
            _check_named_profile(report, resolved_pack, channel, ids)
        elif channel == "place_policy":
            _check_place(report, module, ids)
        else:
            _check_predicate(report, module, ids)
    except Exception as exc:  # noqa: BLE001
        report.fail(f"checking declared ids raised {type(exc).__name__}: {exc}")
    return report


def check_pack_code(
    *,
    pack_root: str | Path,
    files: Sequence[str | Path] | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Check the given files, or every ``code/*.py`` file in the pack."""
    root = Path(pack_root)
    if files is None:
        candidates = sorted((root / "code").glob("*.py")) if (root / "code").is_dir() else []
    else:
        candidates = []
        for item in files:
            path = Path(item)
            if not path.is_absolute():
                path = (Path(repo_root) / path) if repo_root else path
            if path.suffix == ".py" and path.name in CHANNEL_BY_FILENAME and path.exists():
                candidates.append(path)
    reports = [check_pack_code_file(path, pack_root=root) for path in candidates]
    errors = [f"{Path(item.path).name}: {error}" for item in reports for error in item.errors]
    warnings = [f"{Path(item.path).name}: {warning}" for item in reports for warning in item.warnings]
    return {
        "schema_version": 1,
        "ok": not errors,
        "pack_root": str(root),
        "files": [item.to_dict() for item in reports],
        "errors": errors,
        "warnings": warnings,
    }


def render_markdown(result: Mapping[str, Any]) -> str:
    lines = ["# Pack code check", "", f"- Pack: `{result.get('pack_root', '')}`", f"- Status: {'PASS' if result.get('ok') else 'FAIL'}"]
    for item in result.get("files") or []:
        lines.extend(["", f"## {Path(str(item.get('path'))).name} ({item.get('channel')})"])
        lines.append(f"- ids: {', '.join(item.get('declared_ids') or []) or 'none'}")
        lines.append(f"- probed: {', '.join(item.get('checked_ids') or []) or 'none'}")
        for error in item.get("errors") or []:
            lines.append(f"- error: {error}")
        for warning in item.get("warnings") or []:
            lines.append(f"- warning: {warning}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser("Check pack-authored code without a GPU run.")
    parser.add_argument("pack_root", help="e.g. skill_packs/libero90_legacy")
    parser.add_argument("--repo_root", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[4]
    pack_root = Path(args.pack_root)
    if not pack_root.is_absolute():
        pack_root = repo / pack_root
    result = check_pack_code(pack_root=pack_root, repo_root=repo)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result), end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
