"""Core grasp-profile registry for recovery skills.

The default recovery path only owns the generic LIBERO top-down sampler. Tuned
profiles learned on a benchmark live in skill-pack adapters and are loaded only
when the active skill pack points at that adapter. This keeps the problem/debug
adapter and the real cuTAMP backend aligned without making LIBERO-90 tweaks
global behavior.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, List, Mapping, Optional, Tuple

import numpy as np

from .libero_panda_frames import quat_wxyz_to_matrix

DEFAULT_GRASP_SAMPLER_PROFILE = "libero_topdown"
NATIVE_GRASP_SAMPLER_PROFILES = frozenset({"native", "cutamp_native"})
CORE_TOPDOWN_GRASP_SAMPLER_PROFILES = frozenset({"libero_topdown", "hollow_bowl_rim_topdown"})
TOPDOWN_GRASP_SAMPLER_PROFILES = CORE_TOPDOWN_GRASP_SAMPLER_PROFILES
ALLOWED_GRASP_SAMPLER_PROFILES = CORE_TOPDOWN_GRASP_SAMPLER_PROFILES | NATIVE_GRASP_SAMPLER_PROFILES
GRASP_SAMPLER_PROFILE_ALIASES = {"": DEFAULT_GRASP_SAMPLER_PROFILE, "default": DEFAULT_GRASP_SAMPLER_PROFILE}
ALLOWED_SKILL_GRASP_PROFILES = ("default", *sorted(ALLOWED_GRASP_SAMPLER_PROFILES))
GRASP_PROFILE_ADAPTER_PARAM_KEY = "_grasp_profile_adapter_path"


@dataclass(frozen=True)
class LocalGraspSample:
    xyz: Tuple[float, float, float]
    rpy: Tuple[float, float, float]
    metadata: dict[str, Any] = field(default_factory=dict)

    def xyzrpy(self) -> List[float]:
        return [*self.xyz, *self.rpy]


@dataclass(frozen=True)
class GraspProfileAdapter:
    name: str
    path: str
    profile_ids: frozenset[str]
    module: ModuleType

    def sample(self, profile: str, dims: Iterable[float], *, rim: bool, pose: Optional[List[float]] = None) -> List[Any]:
        fn = getattr(self.module, "sample_grasp_profile")
        return list(fn(profile, dims, rim=rim, pose=pose))

    def gripper_width(
        self,
        profile: str,
        dims: Iterable[float],
        *,
        rim: bool = False,
        radius: Optional[float] = None,
        pose: Optional[List[float]] = None,
    ) -> float:
        fn = getattr(self.module, "profile_gripper_width")
        return float(fn(profile, dims, rim=rim, radius=radius, pose=pose))


@dataclass(frozen=True)
class GraspProfileRegistry:
    name: str = "core_grasp_profiles"
    adapters: tuple[GraspProfileAdapter, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.adapters)

    @property
    def profile_ids(self) -> frozenset[str]:
        out = set(ALLOWED_GRASP_SAMPLER_PROFILES)
        for adapter in self.adapters:
            out.update(adapter.profile_ids)
        return frozenset(out)

    @classmethod
    def disabled(cls) -> "GraspProfileRegistry":
        return cls()

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "adapters": [
                {"name": adapter.name, "path": adapter.path, "profiles": sorted(adapter.profile_ids)}
                for adapter in self.adapters
            ],
            "profiles": sorted(self.profile_ids),
        }

    def normalize(self, value: Any) -> str:
        raw = str(value or DEFAULT_GRASP_SAMPLER_PROFILE).strip()
        profile = GRASP_SAMPLER_PROFILE_ALIASES.get(raw, raw)
        if profile not in self.profile_ids:
            allowed = sorted((*self.profile_ids, *GRASP_SAMPLER_PROFILE_ALIASES))
            raise ValueError(f"unknown_grasp_sampler_profile:{raw}; allowed={allowed}")
        return profile

    def adapter_for(self, profile: str) -> GraspProfileAdapter | None:
        normalized = self.normalize(profile)
        for adapter in self.adapters:
            if normalized in adapter.profile_ids:
                return adapter
        return None


_ADAPTER_CACHE: dict[str, GraspProfileAdapter] = {}
CORE_GRASP_PROFILE_REGISTRY = GraspProfileRegistry.disabled()


def _is_abs(path: Path) -> bool:
    return path.is_absolute() or bool(path.drive)


def _load_adapter_module(path: Path) -> ModuleType:
    resolved = path.resolve()
    cache_key = str(resolved)
    cached = _ADAPTER_CACHE.get(cache_key)
    if cached is not None:
        return cached.module
    if not resolved.exists():
        raise FileNotFoundError(f"grasp profile adapter does not exist: {resolved}")
    module_name = f"_libero_grasp_profile_adapter_{abs(hash(cache_key))}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load grasp profile adapter: {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    profile_ids = frozenset(str(item).strip() for item in getattr(module, "PROFILE_IDS", ()) if str(item).strip())
    if not profile_ids:
        raise ValueError(f"grasp profile adapter must expose non-empty PROFILE_IDS: {resolved}")
    for symbol in ("sample_grasp_profile", "profile_gripper_width"):
        if not callable(getattr(module, symbol, None)):
            raise ValueError(f"grasp profile adapter missing callable {symbol}: {resolved}")
    adapter = GraspProfileAdapter(
        name=str(getattr(module, "ADAPTER_NAME", resolved.stem)),
        path=str(resolved),
        profile_ids=profile_ids,
        module=module,
    )
    _ADAPTER_CACHE[cache_key] = adapter
    return module


def load_grasp_profile_adapter(path: str | Path) -> GraspProfileAdapter:
    resolved = Path(path).resolve()
    cache_key = str(resolved)
    cached = _ADAPTER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    _load_adapter_module(resolved)
    return _ADAPTER_CACHE[cache_key]


def load_grasp_profile_registry(
    adapter_path: str | Path | None = None,
    *,
    index_path: str | Path | None = None,
) -> GraspProfileRegistry:
    paths = _adapter_paths(adapter_path, index_path=index_path)
    return registry_from_adapter_paths(paths)


def registry_from_adapter_paths(paths: Iterable[str | Path | None]) -> GraspProfileRegistry:
    adapters: list[GraspProfileAdapter] = []
    seen: set[str] = set()
    for raw in paths:
        if raw in (None, ""):
            continue
        resolved = Path(raw).resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        adapters.append(load_grasp_profile_adapter(resolved))
    if not adapters:
        return CORE_GRASP_PROFILE_REGISTRY
    return GraspProfileRegistry(
        name="+".join(adapter.name for adapter in adapters),
        adapters=tuple(adapters),
    )


def registry_from_recovery_hints(recovery_hints: Mapping[str, Any] | None) -> GraspProfileRegistry:
    params = recovery_hints.get("params") if isinstance(recovery_hints, Mapping) else {}
    if not isinstance(params, Mapping):
        return CORE_GRASP_PROFILE_REGISTRY
    raw = params.get(GRASP_PROFILE_ADAPTER_PARAM_KEY) or params.get("grasp_profile_adapter")
    if raw in (None, ""):
        return CORE_GRASP_PROFILE_REGISTRY
    if isinstance(raw, (list, tuple)):
        return registry_from_adapter_paths(raw)
    return registry_from_adapter_paths([raw])


def _adapter_paths(
    adapter_path: str | Path | None,
    *,
    index_path: str | Path | None = None,
) -> list[Path]:
    paths: list[Path] = []
    if adapter_path not in (None, ""):
        paths.append(Path(adapter_path))
    if index_path not in (None, ""):
        try:
            from experiments.robot.libero.skill_pipeline.schema import load_index
        except Exception:
            load_index = None
        if load_index is not None:
            index = Path(index_path)
            data = load_index(index)
            raw = str(data.get("grasp_profile_adapter") or "").strip()
            if raw:
                candidate = Path(raw)
                paths.append(candidate if _is_abs(candidate) else index.parent / candidate)
            try:
                from experiments.robot.libero.skill_pipeline.adapter_discovery import (
                    infer_pack_code_adapter_path,
                )
            except Exception:
                infer_pack_code_adapter_path = None
            if infer_pack_code_adapter_path is not None:
                inferred = infer_pack_code_adapter_path(index, "grasp_profiles.py")
                if inferred is not None:
                    paths.append(inferred)
    return paths


def normalize_grasp_sampler_profile(value: Any, *, registry: GraspProfileRegistry | None = None) -> str:
    return (registry or CORE_GRASP_PROFILE_REGISTRY).normalize(value)


def is_native_grasp_sampler_profile(profile: str, *, registry: GraspProfileRegistry | None = None) -> bool:
    return normalize_grasp_sampler_profile(profile, registry=registry) in NATIVE_GRASP_SAMPLER_PROFILES


def _dims3(dims: Iterable[float], default: Tuple[float, float, float]) -> np.ndarray:
    arr = np.asarray(list(dims), dtype=np.float64).reshape(-1)
    if arr.size < 3:
        arr = np.pad(arr, (0, 3 - arr.size), constant_values=0.0)
    fallback = np.asarray(default, dtype=np.float64)
    arr = arr[:3]
    arr = np.where(np.abs(arr) > 1e-9, arr, fallback)
    return np.maximum(arr, 1e-4)


def wrap_yaw_rad(value: float) -> float:
    return float((value + np.pi) % (2.0 * np.pi) - np.pi)


def rot_z(yaw: float) -> np.ndarray:
    c = float(np.cos(yaw))
    s = float(np.sin(yaw))
    return np.asarray([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def matrix_to_xyz_rpy(matrix: Any) -> List[float]:
    rot = np.asarray(matrix, dtype=np.float64).reshape(3, 3)
    pitch = float(np.arcsin(np.clip(rot[0, 2], -1.0, 1.0)))
    cp = float(np.cos(pitch))
    if abs(cp) > 1e-8:
        roll = float(np.arctan2(-rot[1, 2], rot[2, 2]))
        yaw = float(np.arctan2(-rot[0, 1], rot[0, 0]))
    else:
        roll = float(np.arctan2(rot[2, 1], rot[1, 1]))
        yaw = 0.0
    return [float(roll), float(pitch), wrap_yaw_rad(yaw)]


def pose7_rotation_matrix(pose: Optional[List[float]]) -> np.ndarray:
    if pose is None:
        return np.eye(3, dtype=np.float64)
    arr = np.asarray(pose, dtype=np.float64).reshape(-1)
    if arr.size < 7:
        return np.eye(3, dtype=np.float64)
    return quat_wxyz_to_matrix(arr[3:7])


def _sample(x: float, y: float, z: float, roll: float, pitch: float, yaw: float, **metadata: Any) -> LocalGraspSample:
    return LocalGraspSample(
        xyz=(float(x), float(y), float(z)),
        rpy=(float(roll), float(pitch), wrap_yaw_rad(float(yaw))),
        metadata=dict(metadata),
    )


def _topdown_samples(dims: Iterable[float], *, rim: bool) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.06, 0.06, 0.04))
    half_x = max(float(ext[0]) * 0.5, 1e-4)
    half_y = max(float(ext[1]) * 0.5, 1e-4)
    half_height = max(float(ext[2]) * 0.5, 1e-4)
    yaw_choices = [0.0, 0.5 * np.pi, np.pi, -0.5 * np.pi, 0.25 * np.pi, -0.25 * np.pi, 0.75 * np.pi, -0.75 * np.pi]
    if rim:
        z_values = [
            max(0.0, half_height - 0.018),
            max(0.0, half_height - 0.028),
        ]
        xy_offsets: list[tuple[float, float]] = []
        for frac in (0.78, 0.86):
            xy_offsets.extend(
                [
                    (frac * half_x, 0.0),
                    (-frac * half_x, 0.0),
                    (0.0, frac * half_y),
                    (0.0, -frac * half_y),
                ]
            )
    else:
        z_values = [max(0.0, half_height - 0.02)]
        lateral = 0.35 * min(half_x, half_y)
        xy_offsets = [
            (0.0, 0.0),
            (lateral, 0.0),
            (-lateral, 0.0),
            (0.0, lateral),
            (0.0, -lateral),
        ]
    samples: list[LocalGraspSample] = []
    for yaw in yaw_choices:
        for z in z_values:
            for dx, dy in xy_offsets:
                samples.append(_sample(dx, dy, z, 0.0, 0.0, yaw, world_yaw=wrap_yaw_rad(yaw)))
    return samples


def sample_grasp_profile(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool,
    pose: Optional[List[float]] = None,
    registry: GraspProfileRegistry | None = None,
) -> List[Any]:
    reg = registry or CORE_GRASP_PROFILE_REGISTRY
    normalized = normalize_grasp_sampler_profile(profile, registry=reg)
    adapter = reg.adapter_for(normalized)
    if adapter is not None:
        return adapter.sample(normalized, dims, rim=rim, pose=pose)
    if normalized in CORE_TOPDOWN_GRASP_SAMPLER_PROFILES or normalized in NATIVE_GRASP_SAMPLER_PROFILES:
        return _topdown_samples(dims, rim=rim)
    raise ValueError(f"grasp sampler profile does not provide top-down samples: {normalized}")


def sample_grasp_profile_xyzrpy(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool,
    pose: Optional[List[float]] = None,
    registry: GraspProfileRegistry | None = None,
) -> List[List[float]]:
    return [sample.xyzrpy() for sample in sample_grasp_profile(profile, dims, rim=rim, pose=pose, registry=registry)]


def profile_gripper_width(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool = False,
    radius: Optional[float] = None,
    pose: Optional[List[float]] = None,
    registry: GraspProfileRegistry | None = None,
) -> float:
    reg = registry or CORE_GRASP_PROFILE_REGISTRY
    normalized = normalize_grasp_sampler_profile(profile, registry=reg)
    adapter = reg.adapter_for(normalized)
    if adapter is not None:
        return adapter.gripper_width(normalized, dims, rim=rim, radius=radius, pose=pose)
    ext = _dims3(dims, (0.06, 0.06, 0.04))
    half = 0.5 * ext
    if normalized in CORE_TOPDOWN_GRASP_SAMPLER_PROFILES or normalized in NATIVE_GRASP_SAMPLER_PROFILES or rim:
        return float(np.clip(1.80 * min(float(half[0]), float(half[1])), 0.025, 0.085))
    fallback_radius = max(float(radius or 0.0), max(float(half[0]), float(half[1])))
    return float(np.clip(2.2 * fallback_radius, 0.025, 0.085))
