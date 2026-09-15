"""Admission checks for skill-owned code changes.

This gate is intentionally narrow. It checks only two things:

1. Candidate code changes stay inside the declared extension boundary.
2. Any skill-owned capability used or added by the patch is registered.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .capabilities import CAPABILITY_CATEGORIES, load_capability_registry
from .predicate_registry import load_predicate_registry
from .schema import SkillSchemaError, load_skill
from .pack_code_check import CHANNEL_BY_FILENAME as PACK_CODE_CHECK_FILENAMES


COMMON_ALLOWED_EXACT = frozenset()
PACK_SKILL_PREFIXES = (
    "skill_packs/generated_v1/skills/",
    "skill_packs/libero90_legacy/skills/",
)
PACK_CODE_PREFIXES = (
    "skill_packs/generated_v1/code/",
    "skill_packs/libero90_legacy/code/",
)
PACK_PROFILE_PREFIXES = (
    "skill_packs/generated_v1/profiles/",
    "skill_packs/libero90_legacy/profiles/",
)
PACK_CAPABILITY_REGISTRY_EXACT = (
    "skill_packs/generated_v1/capabilities.yaml",
    "skill_packs/libero90_legacy/capabilities.yaml",
)
PACK_METADATA_EXACT = (
    *PACK_CAPABILITY_REGISTRY_EXACT,
    "skill_packs/generated_v1/pack.yaml",
    "skill_packs/generated_v1/skills/_index.yaml",
    "skill_packs/libero90_legacy/pack.yaml",
    "skill_packs/libero90_legacy/skills/_index.yaml",
)
COMMON_ALLOWED_PREFIXES = ()
TEST_ALLOWED_PREFIXES = (
    "experiments/robot/libero/skill_pipeline/tests/",
)

ALLOWED_BY_CHANGE_TYPE: dict[str, dict[str, tuple[str, ...]]] = {
    "skill_markdown": {
        "exact": (),
        "prefix": PACK_SKILL_PREFIXES,
    },
    "capability_registry": {
        "exact": (*PACK_METADATA_EXACT, "skill_capabilities/generated_scratch_v1.yaml"),
        "prefix": (),
    },
    "grasp_profile": {
        "exact": (),
        "prefix": (*PACK_CODE_PREFIXES, *PACK_PROFILE_PREFIXES, *TEST_ALLOWED_PREFIXES),
    },
    "grounding_hint": {
        "exact": (),
        "prefix": (
            *PACK_PROFILE_PREFIXES,
            *PACK_CODE_PREFIXES,
            *TEST_ALLOWED_PREFIXES,
        ),
    },
    "geometry_hint": {
        "exact": (),
        "prefix": (
            *PACK_PROFILE_PREFIXES,
            *PACK_CODE_PREFIXES,
            *TEST_ALLOWED_PREFIXES,
        ),
    },
    "place_policy": {
        "exact": (
            "experiments/robot/libero/tiptop_repro/libero_tiptop_executor.py",
            "experiments/robot/libero/tiptop_repro/tamp_scene.py",
        ),
        "prefix": (*PACK_PROFILE_PREFIXES, *PACK_CODE_PREFIXES, *TEST_ALLOWED_PREFIXES),
    },
    "predicate_registry": {
        "exact": (),
        "prefix": (*PACK_PROFILE_PREFIXES, *PACK_CODE_PREFIXES, *TEST_ALLOWED_PREFIXES),
    },
    "repair_profile": {
        "exact": ("experiments/robot/libero/skill_pipeline/repair_profiles.py",),
        "prefix": (
            *PACK_PROFILE_PREFIXES,
            *TEST_ALLOWED_PREFIXES,
        ),
    },
    "diagnostic_signal": {
        "exact": (
            "experiments/robot/libero/skill_pipeline/runner.py",
            "experiments/robot/libero/skill_pipeline/trace_schema.py",
            "experiments/robot/libero/skill_pipeline/trigger_scan.py",
        ),
        "prefix": TEST_ALLOWED_PREFIXES,
    },
}

GRASP_PROFILE_FILE = "experiments/robot/libero/tiptop_repro/grasp_profiles.py"
GRASP_PROFILE_CODE_PREFIXES = PACK_CODE_PREFIXES
GROUNDING_PROFILE_CODE_PREFIXES = PACK_CODE_PREFIXES
GEOMETRY_PROFILE_CODE_PREFIXES = PACK_CODE_PREFIXES
PROFILE_LITERAL_RE = re.compile(
    r"[\"']([a-z][a-z0-9_]*(?:_v\d+|libero_topdown|hollow_bowl_rim_topdown|cutamp_native|native))[\"']"
)


@dataclass(frozen=True)
class CodeAdmissionConfig:
    repo_root: str | Path
    out_dir: str | Path
    manifest_path: str | Path | None = None
    skill_files: Sequence[str | Path] = field(default_factory=tuple)
    index_path: str | Path | None = None
    capability_registry: str | Path | None = None
    predicate_registry: str | Path | None = None
    predicate_adapter: str | Path | None = None
    pack_root: str | Path | None = None
    base_ref: str = "HEAD"
    changed_files: Sequence[str | Path] | None = None
    base_file_texts: Mapping[str, str] = field(default_factory=dict)
    current_file_texts: Mapping[str, str] = field(default_factory=dict)
    allow_empty_diff: bool = True


def _norm_rel(path: str | Path, repo_root: str | Path | None = None) -> str:
    raw = Path(path)
    if raw.is_absolute() and repo_root is not None:
        try:
            raw = raw.resolve().relative_to(Path(repo_root).resolve())
        except ValueError:
            return str(path).replace("\\", "/")
    return raw.as_posix().replace("\\", "/").lstrip("./")


def _pack_root_rel(pack_root: str | Path | None, repo_root: str | Path) -> str:
    if pack_root in (None, ""):
        return ""
    raw = Path(pack_root)
    repo = Path(repo_root).resolve()
    if raw.is_absolute():
        try:
            rel = raw.resolve().relative_to(repo)
        except ValueError:
            return ""
    else:
        rel = raw
    text = rel.as_posix().replace("\\", "/").strip("/")
    return "" if text in {"", "."} else text.rstrip("/")


def _pack_allowed_for_change_type(change_type: str, pack_root: str | Path | None, repo_root: str | Path) -> tuple[set[str], tuple[str, ...]]:
    root = _pack_root_rel(pack_root, repo_root)
    if not root:
        return set(), ()
    exact: set[str] = set()
    prefixes: list[str] = []
    if change_type == "skill_markdown":
        prefixes.append(f"{root}/skills/")
    elif change_type == "capability_registry":
        exact.update(
            {
                f"{root}/capabilities.yaml",
                f"{root}/pack.yaml",
                f"{root}/skills/_index.yaml",
            }
        )
    elif change_type in {"grasp_profile", "grounding_hint", "geometry_hint", "repair_profile", "predicate_registry"}:
        prefixes.extend((f"{root}/code/", f"{root}/profiles/", *TEST_ALLOWED_PREFIXES))
    elif change_type == "place_policy":
        prefixes.extend((f"{root}/code/", f"{root}/profiles/", *TEST_ALLOWED_PREFIXES))
    elif change_type == "diagnostic_signal":
        prefixes.extend((f"{root}/diagnostics/", f"{root}/code/", *TEST_ALLOWED_PREFIXES))
    return exact, tuple(prefixes)


def _pack_code_prefixes(pack_root: str | Path | None, repo_root: str | Path) -> tuple[str, ...]:
    root = _pack_root_rel(pack_root, repo_root)
    return (f"{root}/code/",) if root else ()


def _pack_code_check_files(
    pack_root: str | Path | None,
    changed_files: Sequence[str],
    repo: Path,
) -> list[str]:
    root = _pack_root_rel(pack_root, repo)
    if not root:
        return []
    prefix = f"{root}/code/"
    return [rel for rel in changed_files if rel.startswith(prefix) and Path(rel).name in PACK_CODE_CHECK_FILENAMES]


def run_pack_code_admission_check(
    *,
    config: "CodeAdmissionConfig",
    changed_files: Sequence[str],
    repo: Path,
) -> dict[str, Any]:
    """Probe the pack code this manifest changed, before spending a GPU round.

    The offline scan and same-init validation only exercise the branches an
    episode reaches; this calls every declared id once with the pack's own
    catalogs and reports wrong protocols, non-determinism, side effects, and
    code ids that have no catalog entry.
    """
    rel_files = _pack_code_check_files(config.pack_root, changed_files, repo)
    if not rel_files:
        return {"ok": True, "files": [], "errors": [], "warnings": []}
    from .pack_code_check import check_pack_code

    root_rel = _pack_root_rel(config.pack_root, repo)
    result = check_pack_code(
        pack_root=repo / root_rel,
        files=list(rel_files),
        repo_root=repo,
    )
    errors: list[str] = []
    warnings: list[str] = []
    for item in result.get("files") or []:
        rel = _norm_rel(item.get("path"), repo) or str(item.get("path"))
        errors.extend(f"pack code check ({rel}): {text}" for text in item.get("errors") or [])
        warnings.extend(f"pack code check ({rel}): {text}" for text in item.get("warnings") or [])
    return {"ok": not errors and bool(result.get("ok")), "files": list(result.get("files") or []), "errors": errors, "warnings": warnings}


def _known_capability_registry_paths(
    *,
    capability_registry: str | Path | None,
    pack_root: str | Path | None,
    repo_root: str | Path,
) -> set[str]:
    paths = {*(PACK_CAPABILITY_REGISTRY_EXACT), "skill_capabilities/generated_scratch_v1.yaml"}
    if capability_registry not in (None, ""):
        paths.add(_norm_rel(capability_registry, repo_root))
    root = _pack_root_rel(pack_root, repo_root)
    if root:
        paths.add(f"{root}/capabilities.yaml")
    return {path for path in paths if path}


def _run_git(repo: Path, args: Sequence[str], *, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def _is_git_worktree(repo: Path) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def discover_changed_files(repo_root: str | Path, base_ref: str = "HEAD") -> list[str]:
    repo = Path(repo_root)
    names = _run_git(repo, ["diff", "--name-only", base_ref, "--"]).splitlines()
    untracked = _run_git(repo, ["ls-files", "--others", "--exclude-standard"]).splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for name in [*names, *untracked]:
        rel = _norm_rel(name)
        if rel and rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def _git_file_at(repo: Path, ref: str, rel: str) -> str:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{rel}"],
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else ""


def _read_current_file(repo: Path, rel: str) -> str:
    path = repo / rel
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise SkillSchemaError("PyYAML is required to parse code patch manifests") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SkillSchemaError(f"code patch manifest must be a mapping: {path}")
    return data


def _as_str_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _manifest_capabilities(data: Mapping[str, Any]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {key: [] for key in CAPABILITY_CATEGORIES}
    for group_name in ("capabilities", "new_capabilities", "required_capabilities"):
        group = data.get(group_name) or {}
        if not isinstance(group, Mapping):
            continue
        for category, raw_values in group.items():
            cat = str(category)
            if cat not in merged:
                merged[cat] = []
            for item in _as_str_list(raw_values):
                if item not in merged[cat]:
                    merged[cat].append(item)
    return {key: values for key, values in merged.items() if values}


def _manifest_change_types(data: Mapping[str, Any], manifest_caps: Mapping[str, Sequence[str]]) -> list[str]:
    out: list[str] = []
    for item in _as_str_list(data.get("change_type") or data.get("change_types")):
        if item not in out:
            out.append(item)
    if manifest_caps and "capability_registry" not in out:
        out.append("capability_registry")
    return out


def _allowed_paths(
    change_types: Sequence[str],
    *,
    pack_root: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> tuple[set[str], tuple[str, ...]]:
    exact = set(COMMON_ALLOWED_EXACT)
    prefixes = list(COMMON_ALLOWED_PREFIXES)
    for change_type in change_types:
        key = str(change_type)
        rule = ALLOWED_BY_CHANGE_TYPE.get(key)
        if not rule:
            continue
        exact.update(rule.get("exact", ()))
        prefixes.extend(rule.get("prefix", ()))
        if repo_root is not None:
            pack_exact, pack_prefixes = _pack_allowed_for_change_type(key, pack_root, repo_root)
            exact.update(pack_exact)
            prefixes.extend(pack_prefixes)
    return exact, tuple(dict.fromkeys(prefixes))


def _path_allowed(rel: str, *, exact: set[str], prefixes: Sequence[str]) -> bool:
    return rel in exact or any(rel.startswith(prefix) for prefix in prefixes)


def _is_code_file(rel: str) -> bool:
    return rel.endswith(".py") and not rel.startswith(TEST_ALLOWED_PREFIXES)


def _extract_grasp_profiles(text: str) -> set[str]:
    return set(PROFILE_LITERAL_RE.findall(text or ""))


def _changed_grasp_profiles(
    *,
    repo: Path,
    base_ref: str,
    changed_files: Sequence[str],
    base_file_texts: Mapping[str, str],
    current_file_texts: Mapping[str, str],
    code_prefixes: Sequence[str] = GRASP_PROFILE_CODE_PREFIXES,
) -> list[str]:
    changed_impls = [
        rel
        for rel in changed_files
        if rel == GRASP_PROFILE_FILE
        or (rel.endswith("/grasp_profiles.py") and any(rel.startswith(prefix) for prefix in code_prefixes))
    ]
    added: set[str] = set()
    for rel in changed_impls:
        base_text = base_file_texts.get(rel)
        if base_text is None:
            try:
                base_text = _git_file_at(repo, base_ref, rel)
            except Exception:
                base_text = ""
        current_text = current_file_texts.get(rel)
        if current_text is None:
            current_text = _read_current_file(repo, rel)
        added.update(_extract_grasp_profiles(current_text) - _extract_grasp_profiles(base_text))
    return sorted(added)


def _changed_geometry_profiles(
    *,
    repo: Path,
    base_ref: str,
    changed_files: Sequence[str],
    base_file_texts: Mapping[str, str],
    current_file_texts: Mapping[str, str],
    code_prefixes: Sequence[str] = GEOMETRY_PROFILE_CODE_PREFIXES,
) -> list[str]:
    changed_impls = [
        rel
        for rel in changed_files
        if rel.endswith("/geometry_profiles.py") and any(rel.startswith(prefix) for prefix in code_prefixes)
    ]
    added: set[str] = set()
    for rel in changed_impls:
        base_text = base_file_texts.get(rel)
        if base_text is None:
            try:
                base_text = _git_file_at(repo, base_ref, rel)
            except Exception:
                base_text = ""
        current_text = current_file_texts.get(rel)
        if current_text is None:
            current_text = _read_current_file(repo, rel)
        added.update(_extract_grasp_profiles(current_text) - _extract_grasp_profiles(base_text))
    return sorted(added)


def _changed_grounding_profiles(
    *,
    repo: Path,
    base_ref: str,
    changed_files: Sequence[str],
    base_file_texts: Mapping[str, str],
    current_file_texts: Mapping[str, str],
    code_prefixes: Sequence[str] = GROUNDING_PROFILE_CODE_PREFIXES,
) -> list[str]:
    changed_impls = [
        rel
        for rel in changed_files
        if rel.endswith("/grounding_profiles.py")
        and any(rel.startswith(prefix) for prefix in code_prefixes)
    ]
    added: set[str] = set()
    for rel in changed_impls:
        base_text = base_file_texts.get(rel)
        if base_text is None:
            try:
                base_text = _git_file_at(repo, base_ref, rel)
            except Exception:
                base_text = ""
        current_text = current_file_texts.get(rel)
        if current_text is None:
            current_text = _read_current_file(repo, rel)
        added.update(_extract_grasp_profiles(current_text) - _extract_grasp_profiles(base_text))
    return sorted(added)


def _implemented_grasp_profiles(implementation_texts: Mapping[str, str]) -> set[str]:
    from experiments.robot.libero.tiptop_repro.grasp_profiles import ALLOWED_GRASP_SAMPLER_PROFILES

    out = {str(item) for item in ALLOWED_GRASP_SAMPLER_PROFILES}
    for text in implementation_texts.values():
        out.update(_extract_grasp_profiles(text))
    return out


def _adapter_registered_grasp_profiles(index_path: str | Path | None) -> set[str]:
    if not index_path:
        return set()
    try:
        from experiments.robot.libero.tiptop_repro.grasp_profiles import load_grasp_profile_registry

        return {str(item) for item in load_grasp_profile_registry(index_path=index_path).profile_ids}
    except Exception:
        return set()


def _implementation_texts(
    *,
    repo: Path,
    changed_files: Sequence[str],
    current_file_texts: Mapping[str, str],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in changed_files:
        if not _is_code_file(rel):
            continue
        out[rel] = current_file_texts.get(rel, _read_current_file(repo, rel))
    return out


def _capability_appears_in_code(value: str, texts: Mapping[str, str]) -> bool:
    return any(value in text for text in texts.values())


def render_code_admission_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Code Admission Report",
        "",
        f"- Status: {'PASS' if report.get('ok') else 'FAIL'}",
        f"- Base ref: `{report.get('base_ref', '')}`",
        f"- Manifest: `{report.get('manifest_path', '')}`",
        f"- Changed files: {len(report.get('changed_files') or [])}",
        "",
        "## Errors",
        "",
    ]
    errors = list(report.get("errors") or [])
    lines.extend(f"- {item}" for item in errors) if errors else lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    warnings = list(report.get("warnings") or [])
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- none")
    lines.extend(["", "## Boundary", ""])
    boundary = dict(report.get("boundary") or {})
    lines.append(f"- Change types: `{', '.join(report.get('change_types') or [])}`")
    lines.append(f"- Violations: {len(boundary.get('violations') or [])}")
    for rel in boundary.get("violations") or []:
        lines.append(f"  - `{rel}`")
    lines.extend(["", "## Capabilities", ""])
    caps = dict(report.get("manifest_capabilities") or {})
    if caps:
        for category, values in caps.items():
            lines.append(f"- {category}: `{', '.join(str(item) for item in values)}`")
    else:
        lines.append("- none declared in manifest")
    added = dict(report.get("code_added_capabilities") or {})
    if added:
        lines.extend(["", "## Code Added Capabilities", ""])
        for category, values in added.items():
            lines.append(f"- {category}: `{', '.join(str(item) for item in values)}`")
    pack_code = dict(report.get("pack_code_check") or {})
    if pack_code.get("files"):
        lines.extend(["", "## Pack Code Check", ""])
        for item in pack_code["files"]:
            status = "ok" if item.get("ok") else "FAILED"
            lines.append(f"- {Path(str(item.get('path'))).name}: {status} (channel `{item.get('channel')}`)")
            lines.append(f"  - ids: {', '.join(item.get('declared_ids') or []) or 'none'}")
            lines.append(f"  - probed: {', '.join(item.get('checked_ids') or []) or 'none'}")
            for error in item.get("errors") or []:
                lines.append(f"  - error: {error}")
            for warning in item.get("warnings") or []:
                lines.append(f"  - warning: {warning}")
    return "\n".join(lines) + "\n"


def run_code_admission(config: CodeAdmissionConfig) -> dict[str, Any]:
    repo = Path(config.repo_root).resolve()
    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = Path(config.manifest_path).resolve() if config.manifest_path else None
    manifest: dict[str, Any] = {}
    if manifest_path is not None:
        try:
            manifest = _load_yaml(manifest_path)
        except Exception as exc:
            errors.append(f"manifest: {type(exc).__name__}: {exc}")

    manifest_caps = _manifest_capabilities(manifest)
    change_types = _manifest_change_types(manifest, manifest_caps)
    manifest_touched = {_norm_rel(path, repo) for path in _as_str_list(manifest.get("touched_files"))}
    if config.changed_files is not None:
        changed_files = [_norm_rel(path, repo) for path in config.changed_files]
    elif manifest_touched and not _is_git_worktree(repo):
        changed_files = sorted(manifest_touched)
        warnings.append(
            "repo_root is not a git worktree; using manifest.touched_files as the code-admission changed-file set"
        )
    else:
        changed_files = discover_changed_files(repo, config.base_ref)
    changed_files = sorted(dict.fromkeys(path for path in changed_files if path))

    if not changed_files and not config.allow_empty_diff:
        errors.append("code admission found no changed files")

    code_changed = [rel for rel in changed_files if _is_code_file(rel)]
    capability_registry_paths = _known_capability_registry_paths(
        capability_registry=config.capability_registry,
        pack_root=config.pack_root,
        repo_root=repo,
    )
    registry_changed = [
        rel
        for rel in changed_files
        if rel in capability_registry_paths
    ]
    if code_changed and manifest_path is None:
        errors.append("code changes require a code patch manifest")
    if registry_changed and manifest_path is None:
        errors.append("capability registry changes require a code patch manifest")
    if registry_changed and not manifest_caps:
        errors.append("capability registry changes require manifest capabilities")
    if code_changed and not change_types:
        errors.append("code changes require manifest.change_type")

    if code_changed and not manifest_touched:
        errors.append("code changes require manifest.touched_files")
    undeclared_touched = sorted(rel for rel in changed_files if manifest_touched and rel not in manifest_touched)
    if undeclared_touched:
        errors.append(f"changed files not listed in manifest.touched_files: {undeclared_touched[:10]}")
    unused_touched = sorted(rel for rel in manifest_touched if rel not in set(changed_files))
    if unused_touched:
        warnings.append(f"manifest.touched_files includes unchanged files: {unused_touched[:10]}")

    unknown_types = sorted(set(change_types) - set(ALLOWED_BY_CHANGE_TYPE))
    if unknown_types:
        errors.append(f"unknown code change_type values: {unknown_types}")

    exact, prefixes = _allowed_paths(change_types, pack_root=config.pack_root, repo_root=repo)
    violations = sorted(rel for rel in changed_files if not _path_allowed(rel, exact=exact, prefixes=prefixes))
    if violations:
        errors.append(f"changed files outside declared code-admission boundary: {violations[:10]}")

    registry = None
    registry_summary: dict[str, Any] = {}
    try:
        registry = load_capability_registry(config.capability_registry, index_path=config.index_path)
        registry_summary = registry.summary()
    except Exception as exc:
        errors.append(f"capability registry: {type(exc).__name__}: {exc}")

    predicate_registry = None
    predicate_registry_summary: dict[str, Any] = {}
    try:
        predicate_registry = load_predicate_registry(
            config.predicate_registry,
            adapter_path=config.predicate_adapter,
            index_path=config.index_path,
        )
        predicate_registry_summary = predicate_registry.summary()
    except Exception as exc:
        errors.append(f"predicate registry: {type(exc).__name__}: {exc}")

    skill_audits: list[dict[str, Any]] = []
    if registry is not None:
        for skill_file in config.skill_files:
            try:
                spec = load_skill(skill_file, predicate_registry=predicate_registry)
                audit = registry.audit_skill(spec)
                skill_audits.append({"skill_file": str(skill_file), "skill_id": spec.id, **audit.to_dict()})
                errors.extend(f"{spec.id}: capability: {item}" for item in audit.errors)
                warnings.extend(f"{spec.id}: capability: {item}" for item in audit.warnings)
            except Exception as exc:
                errors.append(f"skill capability audit failed for {skill_file}: {type(exc).__name__}: {exc}")

    pack_code_check = run_pack_code_admission_check(
        config=config,
        changed_files=changed_files,
        repo=repo,
    )
    errors.extend(pack_code_check.get("errors") or [])
    warnings.extend(pack_code_check.get("warnings") or [])

    pack_code_prefixes = _pack_code_prefixes(config.pack_root, repo)
    grasp_code_prefixes = tuple(dict.fromkeys((*GRASP_PROFILE_CODE_PREFIXES, *pack_code_prefixes)))
    geometry_code_prefixes = tuple(dict.fromkeys((*GEOMETRY_PROFILE_CODE_PREFIXES, *pack_code_prefixes)))
    grounding_code_prefixes = tuple(dict.fromkeys((*GROUNDING_PROFILE_CODE_PREFIXES, *pack_code_prefixes)))
    code_added_profiles = _changed_grasp_profiles(
        repo=repo,
        base_ref=config.base_ref,
        changed_files=changed_files,
        base_file_texts=config.base_file_texts,
        current_file_texts=config.current_file_texts,
        code_prefixes=grasp_code_prefixes,
    )
    code_added_geometry_profiles = _changed_geometry_profiles(
        repo=repo,
        base_ref=config.base_ref,
        changed_files=changed_files,
        base_file_texts=config.base_file_texts,
        current_file_texts=config.current_file_texts,
        code_prefixes=geometry_code_prefixes,
    )
    code_added_grounding_profiles = _changed_grounding_profiles(
        repo=repo,
        base_ref=config.base_ref,
        changed_files=changed_files,
        base_file_texts=config.base_file_texts,
        current_file_texts=config.current_file_texts,
        code_prefixes=grounding_code_prefixes,
    )
    code_added_capabilities = {}
    if code_added_profiles:
        code_added_capabilities["grasp_profiles"] = code_added_profiles
    if code_added_grounding_profiles:
        code_added_capabilities["grounding_profiles"] = code_added_grounding_profiles
    if code_added_geometry_profiles:
        code_added_capabilities["geometry_profiles"] = code_added_geometry_profiles
    declared_profiles = set(manifest_caps.get("grasp_profiles") or [])
    declared_grounding_profiles = set(manifest_caps.get("grounding_profiles") or [])
    declared_geometry_profiles = set(manifest_caps.get("geometry_profiles") or [])
    registry_profiles = set((registry.capabilities.get("grasp_profiles") if registry is not None else []) or [])
    registry_grounding_profiles = set((registry.capabilities.get("grounding_profiles") if registry is not None else []) or [])
    registry_geometry_profiles = set((registry.capabilities.get("geometry_profiles") if registry is not None else []) or [])
    impl_texts = _implementation_texts(
        repo=repo,
        changed_files=changed_files,
        current_file_texts=config.current_file_texts,
    )
    implemented_profiles = _implemented_grasp_profiles(impl_texts)
    implemented_profiles.update(_adapter_registered_grasp_profiles(config.index_path))

    for profile in code_added_profiles:
        if profile not in declared_profiles:
            errors.append(f"added grasp profile is not declared in manifest capabilities: {profile}")
        if registry is not None and profile not in registry_profiles:
            errors.append(f"added grasp profile is not registered: {profile}")

    for profile in code_added_geometry_profiles:
        if profile not in declared_geometry_profiles:
            errors.append(f"added geometry profile is not declared in manifest capabilities: {profile}")
        if registry is not None and profile not in registry_geometry_profiles:
            errors.append(f"added geometry profile is not registered: {profile}")

    for profile in code_added_grounding_profiles:
        if profile not in declared_grounding_profiles:
            errors.append(f"added grounding profile is not declared in manifest capabilities: {profile}")
        if registry is not None and profile not in registry_grounding_profiles:
            errors.append(f"added grounding profile is not registered: {profile}")

    for category, values in manifest_caps.items():
        if category not in CAPABILITY_CATEGORIES:
            errors.append(f"unknown capability category in manifest: {category}")
            continue
        registered = set((registry.capabilities.get(category) if registry is not None else []) or [])
        for value in values:
            if registry is not None and value not in registered:
                errors.append(f"manifest capability is not registered: {category}:{value}")
            if category == "grasp_profiles":
                if value not in implemented_profiles:
                    errors.append(f"manifest grasp profile is not implemented: {value}")
            elif code_changed and not _capability_appears_in_code(value, impl_texts):
                errors.append(f"manifest capability is not mentioned in changed code: {category}:{value}")

    result: dict[str, Any] = {
        "schema_version": 1,
        "ok": not errors,
        "repo_root": str(repo),
        "pack_root": str(config.pack_root or ""),
        "base_ref": config.base_ref,
        "manifest_path": str(manifest_path) if manifest_path else "",
        "manifest": manifest,
        "change_types": change_types,
        "changed_files": changed_files,
        "boundary": {
            "allowed_exact": sorted(exact),
            "allowed_prefixes": list(prefixes),
            "capability_registry_paths": sorted(capability_registry_paths),
            "violations": violations,
            "undeclared_touched": undeclared_touched,
            "unused_touched": unused_touched,
        },
        "capability_registry": registry_summary,
        "predicate_registry": predicate_registry_summary,
        "manifest_capabilities": manifest_caps,
        "code_added_capabilities": code_added_capabilities,
        "pack_code_check": pack_code_check,
        "skill_capability_audits": skill_audits,
        "errors": errors,
        "warnings": warnings,
    }
    json_path = out_dir / "code_admission_result.json"
    md_path = out_dir / "code_admission_report.md"
    result["result_json"] = str(json_path)
    result["result_markdown"] = str(md_path)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_code_admission_markdown(result), encoding="utf-8")
    return result
