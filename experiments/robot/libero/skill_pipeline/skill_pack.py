"""Skill-pack path resolution for isolated recovery skill libraries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_skill_index(repo: str | Path | None = None) -> Path:
    root = Path(repo) if repo is not None else repo_root()
    return root / "skills" / "_index.yaml"


def default_diagnostic_registry() -> Path:
    return Path(__file__).resolve().parent / "diagnostics" / "registry.yaml"


def _is_abs(path: Path) -> bool:
    return path.is_absolute() or bool(path.drive)


def _repo_path(root: Path, value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value)
    return path if _is_abs(path) else root / path


def _pack_location(value: str | Path, root: Path) -> Path:
    raw = Path(value)
    if _is_abs(raw):
        return raw
    candidates: list[Path] = []
    if len(raw.parts) == 1:
        candidates.append(root / "skill_packs" / raw)
    candidates.append(root / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - covered by schema tests elsewhere.
        raise RuntimeError("PyYAML is required to parse skill packs") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"skill pack manifest must be a mapping: {path}")
    return data


def _pack_path(pack_root: Path, value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value)
    return path if _is_abs(path) else pack_root / path


def _registry_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    rel = str(data.get("capability_registry") or "").strip()
    if not rel:
        return None
    path = Path(rel)
    return path if _is_abs(path) else index_path.parent / path


def _grasp_adapter_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    rel = str(data.get("grasp_profile_adapter") or "").strip()
    if not rel:
        return None
    path = Path(rel)
    return path if _is_abs(path) else index_path.parent / path


def _place_policy_adapter_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    for key in ("place_policy_adapter", "place_profile_adapter"):
        rel = str(data.get(key) or "").strip()
        if not rel:
            continue
        path = Path(rel)
        return path if _is_abs(path) else index_path.parent / path
    return None


def _geometry_adapter_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    rel = str(data.get("geometry_profile_adapter") or "").strip()
    if not rel:
        return None
    path = Path(rel)
    return path if _is_abs(path) else index_path.parent / path


def _grounding_adapter_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    rel = str(data.get("grounding_profile_adapter") or "").strip()
    if not rel:
        return None
    path = Path(rel)
    return path if _is_abs(path) else index_path.parent / path


def _predicate_adapter_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    for key in ("predicate_adapter", "predicate_registry_adapter"):
        rel = str(data.get(key) or "").strip()
        if not rel:
            continue
        path = Path(rel)
        return path if _is_abs(path) else index_path.parent / path
    return None


def _predicate_registry_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    rel = str(data.get("predicate_registry") or "").strip()
    if not rel:
        return None
    path = Path(rel)
    return path if _is_abs(path) else index_path.parent / path


def _grounding_profile_registry_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    rel = str(data.get("grounding_profile_registry") or "").strip()
    if not rel:
        return None
    path = Path(rel)
    return path if _is_abs(path) else index_path.parent / path


def _repair_profile_registry_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    rel = str(data.get("repair_profile_registry") or "").strip()
    if not rel:
        return None
    path = Path(rel)
    return path if _is_abs(path) else index_path.parent / path


def _place_profile_registry_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    rel = str(data.get("place_profile_registry") or "").strip()
    if not rel:
        return None
    path = Path(rel)
    return path if _is_abs(path) else index_path.parent / path


def _geometry_profile_registry_from_index(index_path: Path) -> Path | None:
    if not index_path.exists():
        return None
    data = _load_yaml(index_path)
    rel = str(data.get("geometry_profile_registry") or "").strip()
    if not rel:
        return None
    path = Path(rel)
    return path if _is_abs(path) else index_path.parent / path


@dataclass(frozen=True)
class SkillPack:
    name: str
    root: Path
    manifest_path: Path | None
    skills_dir: Path
    skill_index: Path
    capability_registry: Path | None
    diagnostic_signal_registry: Path | None
    repair_profile_registry: Path | None
    place_profile_registry: Path | None
    place_policy_adapter: Path | None
    grasp_profile_adapter: Path | None
    grounding_profile_adapter: Path | None
    geometry_profile_adapter: Path | None
    grounding_profile_registry: Path | None
    geometry_profile_registry: Path | None
    predicate_registry: Path | None
    predicate_adapter: Path | None
    description: str = ""

    def to_summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "root": str(self.root),
            "manifest_path": str(self.manifest_path) if self.manifest_path else "",
            "skills_dir": str(self.skills_dir),
            "skill_index": str(self.skill_index),
            "capability_registry": str(self.capability_registry or ""),
            "diagnostic_signal_registry": str(self.diagnostic_signal_registry or ""),
            "repair_profile_registry": str(self.repair_profile_registry or ""),
            "place_profile_registry": str(self.place_profile_registry or ""),
            "place_policy_adapter": str(self.place_policy_adapter or ""),
            "grasp_profile_adapter": str(self.grasp_profile_adapter or ""),
            "grounding_profile_adapter": str(self.grounding_profile_adapter or ""),
            "geometry_profile_adapter": str(self.geometry_profile_adapter or ""),
            "grounding_profile_registry": str(self.grounding_profile_registry or ""),
            "geometry_profile_registry": str(self.geometry_profile_registry or ""),
            "predicate_registry": str(self.predicate_registry or ""),
            "predicate_adapter": str(self.predicate_adapter or ""),
            "description": self.description,
        }


@dataclass(frozen=True)
class ResolvedSkillConfig:
    skill_pack: SkillPack | None
    skills_dir: Path
    skill_index: Path
    capability_registry: Path | None
    diagnostic_signal_registry: Path | None
    repair_profile_registry: Path | None
    place_profile_registry: Path | None
    place_policy_adapter: Path | None
    grasp_profile_adapter: Path | None
    grounding_profile_adapter: Path | None
    geometry_profile_adapter: Path | None
    grounding_profile_registry: Path | None
    geometry_profile_registry: Path | None
    predicate_registry: Path | None
    predicate_adapter: Path | None

    def to_summary(self) -> dict[str, Any]:
        return {
            "skill_pack": self.skill_pack.to_summary() if self.skill_pack else {},
            "skills_dir": str(self.skills_dir),
            "skill_index": str(self.skill_index),
            "capability_registry": str(self.capability_registry or ""),
            "diagnostic_signal_registry": str(self.diagnostic_signal_registry or ""),
            "repair_profile_registry": str(self.repair_profile_registry or ""),
            "place_profile_registry": str(self.place_profile_registry or ""),
            "place_policy_adapter": str(self.place_policy_adapter or ""),
            "grasp_profile_adapter": str(self.grasp_profile_adapter or ""),
            "grounding_profile_adapter": str(self.grounding_profile_adapter or ""),
            "geometry_profile_adapter": str(self.geometry_profile_adapter or ""),
            "grounding_profile_registry": str(self.grounding_profile_registry or ""),
            "geometry_profile_registry": str(self.geometry_profile_registry or ""),
            "predicate_registry": str(self.predicate_registry or ""),
            "predicate_adapter": str(self.predicate_adapter or ""),
        }


def resolve_skill_pack(skill_pack: str | Path, *, repo: str | Path | None = None) -> SkillPack:
    """Resolve a pack name, pack directory, pack.yaml, or legacy skill index."""
    if str(skill_pack).strip() == "":
        raise ValueError("skill_pack must not be empty")
    root = Path(repo) if repo is not None else repo_root()
    location = _pack_location(skill_pack, root)

    if location.is_file() and location.name == "_index.yaml":
        index_path = location
        skills_dir = index_path.parent
        return SkillPack(
            name=skills_dir.name,
            root=skills_dir,
            manifest_path=None,
            skills_dir=skills_dir,
            skill_index=index_path,
            capability_registry=_registry_from_index(index_path),
            diagnostic_signal_registry=None,
            repair_profile_registry=_repair_profile_registry_from_index(index_path),
            place_profile_registry=_place_profile_registry_from_index(index_path),
            place_policy_adapter=_place_policy_adapter_from_index(index_path),
            grasp_profile_adapter=_grasp_adapter_from_index(index_path),
            grounding_profile_adapter=_grounding_adapter_from_index(index_path),
            geometry_profile_adapter=_geometry_adapter_from_index(index_path),
            grounding_profile_registry=_grounding_profile_registry_from_index(index_path),
            geometry_profile_registry=_geometry_profile_registry_from_index(index_path),
            predicate_registry=_predicate_registry_from_index(index_path),
            predicate_adapter=_predicate_adapter_from_index(index_path),
            description="Legacy skill directory resolved as a pack.",
        )

    manifest_path = location if location.is_file() else location / "pack.yaml"
    if not manifest_path.exists():
        fallback_index = location / "_index.yaml"
        if fallback_index.exists():
            return resolve_skill_pack(fallback_index, repo=root)
        raise FileNotFoundError(f"skill pack manifest does not exist: {manifest_path}")

    pack_root = manifest_path.parent
    data = _load_yaml(manifest_path)
    name = str(data.get("name") or pack_root.name)
    skills_dir = _pack_path(pack_root, data.get("skills_dir") or "skills")
    if skills_dir is None:
        skills_dir = pack_root / "skills"
    skill_index = _pack_path(pack_root, data.get("skill_index") or (Path(data.get("skills_dir") or "skills") / "_index.yaml"))
    if skill_index is None:
        skill_index = skills_dir / "_index.yaml"
    capability_registry = _pack_path(pack_root, data.get("capability_registry"))
    if capability_registry is None:
        capability_registry = _registry_from_index(skill_index)
    diagnostic_signal_registry = _pack_path(pack_root, data.get("diagnostic_signal_registry"))
    repair_profile_registry = _pack_path(pack_root, data.get("repair_profile_registry"))
    if repair_profile_registry is None:
        inferred = pack_root / "profiles" / "repair.yaml"
        repair_profile_registry = inferred if inferred.exists() else None
    place_profile_registry = _pack_path(pack_root, data.get("place_profile_registry"))
    if place_profile_registry is None:
        inferred = pack_root / "profiles" / "place.yaml"
        place_profile_registry = inferred if inferred.exists() else None
    place_policy_adapter = _pack_path(pack_root, data.get("place_policy_adapter") or data.get("place_profile_adapter"))
    if place_policy_adapter is None:
        inferred = pack_root / "code" / "place_policies.py"
        place_policy_adapter = inferred if inferred.exists() else None
    grasp_profile_adapter = _pack_path(pack_root, data.get("grasp_profile_adapter"))
    grounding_profile_adapter = _pack_path(pack_root, data.get("grounding_profile_adapter"))
    geometry_profile_adapter = _pack_path(pack_root, data.get("geometry_profile_adapter"))
    grounding_profile_registry = _pack_path(pack_root, data.get("grounding_profile_registry"))
    if grounding_profile_registry is None:
        inferred = pack_root / "profiles" / "grounding.yaml"
        grounding_profile_registry = inferred if inferred.exists() else None
    geometry_profile_registry = _pack_path(pack_root, data.get("geometry_profile_registry"))
    if geometry_profile_registry is None:
        inferred = pack_root / "profiles" / "geometry.yaml"
        geometry_profile_registry = inferred if inferred.exists() else None
    predicate_registry = _pack_path(pack_root, data.get("predicate_registry"))
    if predicate_registry is None:
        inferred = pack_root / "profiles" / "predicates.yaml"
        predicate_registry = inferred if inferred.exists() else None
    predicate_adapter = _pack_path(pack_root, data.get("predicate_adapter") or data.get("predicate_registry_adapter"))
    if predicate_adapter is None:
        inferred = pack_root / "code" / "predicates.py"
        predicate_adapter = inferred if inferred.exists() else None
    return SkillPack(
        name=name,
        root=pack_root,
        manifest_path=manifest_path,
        skills_dir=skills_dir,
        skill_index=skill_index,
        capability_registry=capability_registry,
        diagnostic_signal_registry=diagnostic_signal_registry,
        repair_profile_registry=repair_profile_registry,
        place_profile_registry=place_profile_registry,
        place_policy_adapter=place_policy_adapter,
        grasp_profile_adapter=grasp_profile_adapter,
        grounding_profile_adapter=grounding_profile_adapter,
        geometry_profile_adapter=geometry_profile_adapter,
        grounding_profile_registry=grounding_profile_registry,
        geometry_profile_registry=geometry_profile_registry,
        predicate_registry=predicate_registry,
        predicate_adapter=predicate_adapter,
        description=str(data.get("description") or ""),
    )


def resolve_skill_config(
    *,
    skill_pack: str | Path | None = None,
    skills_dir: str | Path | None = None,
    skill_index: str | Path | None = None,
    capability_registry: str | Path | None = None,
    diagnostic_signal_registry: str | Path | None = None,
    repair_profile_registry: str | Path | None = None,
    place_profile_registry: str | Path | None = None,
    place_policy_adapter: str | Path | None = None,
    grasp_profile_adapter: str | Path | None = None,
    grounding_profile_adapter: str | Path | None = None,
    geometry_profile_adapter: str | Path | None = None,
    grounding_profile_registry: str | Path | None = None,
    geometry_profile_registry: str | Path | None = None,
    predicate_registry: str | Path | None = None,
    predicate_adapter: str | Path | None = None,
    repo: str | Path | None = None,
    default_index: str | Path | None = None,
    default_diagnostic_registry_path: str | Path | None = None,
) -> ResolvedSkillConfig:
    """Resolve runtime skill paths while preserving old explicit-path behavior."""
    root = Path(repo) if repo is not None else repo_root()
    pack = resolve_skill_pack(skill_pack, repo=root) if skill_pack else None

    resolved_skills_dir = _repo_path(root, skills_dir)
    resolved_skill_index = _repo_path(root, skill_index)
    resolved_capability_registry = _repo_path(root, capability_registry)
    resolved_diagnostic_registry = _repo_path(root, diagnostic_signal_registry)
    resolved_repair_profile_registry = _repo_path(root, repair_profile_registry)
    resolved_place_profile_registry = _repo_path(root, place_profile_registry)
    resolved_place_policy_adapter = _repo_path(root, place_policy_adapter)
    resolved_grasp_profile_adapter = _repo_path(root, grasp_profile_adapter)
    resolved_grounding_profile_adapter = _repo_path(root, grounding_profile_adapter)
    resolved_geometry_profile_adapter = _repo_path(root, geometry_profile_adapter)
    resolved_grounding_profile_registry = _repo_path(root, grounding_profile_registry)
    resolved_geometry_profile_registry = _repo_path(root, geometry_profile_registry)
    resolved_predicate_registry = _repo_path(root, predicate_registry)
    resolved_predicate_adapter = _repo_path(root, predicate_adapter)
    explicit_skill_index = resolved_skill_index is not None

    if pack is not None:
        if resolved_skill_index is None:
            resolved_skill_index = pack.skill_index
        if resolved_skills_dir is None and not explicit_skill_index:
            resolved_skills_dir = pack.skills_dir
        if resolved_capability_registry is None:
            resolved_capability_registry = pack.capability_registry
        if resolved_diagnostic_registry is None:
            resolved_diagnostic_registry = pack.diagnostic_signal_registry
        if resolved_repair_profile_registry is None:
            resolved_repair_profile_registry = pack.repair_profile_registry
        if resolved_place_profile_registry is None:
            resolved_place_profile_registry = pack.place_profile_registry
        if resolved_place_policy_adapter is None:
            resolved_place_policy_adapter = pack.place_policy_adapter
        if resolved_grasp_profile_adapter is None:
            resolved_grasp_profile_adapter = pack.grasp_profile_adapter
        if resolved_grounding_profile_adapter is None:
            resolved_grounding_profile_adapter = pack.grounding_profile_adapter
        if resolved_geometry_profile_adapter is None:
            resolved_geometry_profile_adapter = pack.geometry_profile_adapter
        if resolved_grounding_profile_registry is None:
            resolved_grounding_profile_registry = pack.grounding_profile_registry
        if resolved_geometry_profile_registry is None:
            resolved_geometry_profile_registry = pack.geometry_profile_registry
        if resolved_predicate_registry is None:
            resolved_predicate_registry = pack.predicate_registry
        if resolved_predicate_adapter is None:
            resolved_predicate_adapter = pack.predicate_adapter

    if resolved_skill_index is None:
        if resolved_skills_dir is not None:
            resolved_skill_index = resolved_skills_dir / "_index.yaml"
        elif default_index is not None:
            resolved_skill_index = _repo_path(root, default_index)
        else:
            resolved_skill_index = default_skill_index(root)
    if resolved_skills_dir is None:
        resolved_skills_dir = resolved_skill_index.parent
    if resolved_diagnostic_registry is None:
        if default_diagnostic_registry_path is not None:
            resolved_diagnostic_registry = _repo_path(root, default_diagnostic_registry_path)
        else:
            resolved_diagnostic_registry = default_diagnostic_registry()
    if resolved_grasp_profile_adapter is None:
        resolved_grasp_profile_adapter = _grasp_adapter_from_index(resolved_skill_index)
    if resolved_place_policy_adapter is None:
        resolved_place_policy_adapter = _place_policy_adapter_from_index(resolved_skill_index)
    if resolved_repair_profile_registry is None:
        resolved_repair_profile_registry = _repair_profile_registry_from_index(resolved_skill_index)
    if resolved_place_profile_registry is None:
        resolved_place_profile_registry = _place_profile_registry_from_index(resolved_skill_index)
    if resolved_grounding_profile_adapter is None:
        resolved_grounding_profile_adapter = _grounding_adapter_from_index(resolved_skill_index)
    if resolved_geometry_profile_adapter is None:
        resolved_geometry_profile_adapter = _geometry_adapter_from_index(resolved_skill_index)
    if resolved_grounding_profile_registry is None:
        resolved_grounding_profile_registry = _grounding_profile_registry_from_index(resolved_skill_index)
    if resolved_geometry_profile_registry is None:
        resolved_geometry_profile_registry = _geometry_profile_registry_from_index(resolved_skill_index)
    if resolved_predicate_registry is None:
        resolved_predicate_registry = _predicate_registry_from_index(resolved_skill_index)
    if resolved_predicate_adapter is None:
        resolved_predicate_adapter = _predicate_adapter_from_index(resolved_skill_index)

    return ResolvedSkillConfig(
        skill_pack=pack,
        skills_dir=resolved_skills_dir,
        skill_index=resolved_skill_index,
        capability_registry=resolved_capability_registry,
        diagnostic_signal_registry=resolved_diagnostic_registry,
        repair_profile_registry=resolved_repair_profile_registry,
        place_profile_registry=resolved_place_profile_registry,
        place_policy_adapter=resolved_place_policy_adapter,
        grasp_profile_adapter=resolved_grasp_profile_adapter,
        grounding_profile_adapter=resolved_grounding_profile_adapter,
        geometry_profile_adapter=resolved_geometry_profile_adapter,
        grounding_profile_registry=resolved_grounding_profile_registry,
        geometry_profile_registry=resolved_geometry_profile_registry,
        predicate_registry=resolved_predicate_registry,
        predicate_adapter=resolved_predicate_adapter,
    )
