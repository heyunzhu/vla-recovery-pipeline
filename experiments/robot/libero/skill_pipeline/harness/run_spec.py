from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_TASK_SPLIT_RE = re.compile(r"[\s,]+")


def parse_task_ids(value: Any) -> list[int]:
    """Parse task ids from YAML values such as `47-54`, `47,48`, or lists."""

    if value is None or value == "":
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, (list, tuple)):
        ids: list[int] = []
        for item in value:
            ids.extend(parse_task_ids(item))
        return _dedupe(ids)
    text = str(value).strip()
    if not text:
        return []
    ids: list[int] = []
    for part in _TASK_SPLIT_RE.split(text):
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            step = 1 if end >= start else -1
            ids.extend(range(start, end + step, step))
        else:
            ids.append(int(part))
    return _dedupe(ids)


def _dedupe(ids: list[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def parse_gpu_ids(value: Any) -> list[int]:
    ids = parse_task_ids(value)
    if not ids:
        raise ValueError("at least one GPU id is required")
    return ids


def split_tasks(tasks: list[int], gpus: list[int]) -> list[tuple[int, list[int]]]:
    """Split tasks into contiguous, balanced GPU lanes."""

    if not gpus:
        raise ValueError("gpus must not be empty")
    if not tasks:
        return []
    lanes: list[tuple[int, list[int]]] = []
    n = len(tasks)
    m = min(len(gpus), n)
    for idx, gpu in enumerate(gpus[:m]):
        start = idx * n // m
        end = (idx + 1) * n // m
        chunk = tasks[start:end]
        if chunk:
            lanes.append((gpu, chunk))
    return lanes


@dataclass(frozen=True)
class RealCutampSpec:
    enabled: bool = True
    require_feasible: bool = True
    robot: str = "panda"
    grasp_dof: int = 6
    num_particles: int = 64
    num_opt_steps: int = 40
    max_loop_dur: float = 20.0
    curobo_plan: bool = True
    serialize_trajectories: bool = True
    prefer_executable_plan: bool = True
    require_executable_plan: bool = True
    runner_timeout_sec: float = 360.0
    table_proxy_profile: str = "thin_clipped_lowered"
    static_context_collision_mode: str = "all"

    @classmethod
    def from_mapping(cls, data: Any) -> "RealCutampSpec":
        if data is None:
            return cls()
        if isinstance(data, bool):
            return cls(enabled=data)
        if not isinstance(data, dict):
            raise TypeError(f"real_cutamp must be a mapping or bool, got {type(data).__name__}")
        known = {field.name for field in dataclasses.fields(cls)}
        kwargs = {key: value for key, value in data.items() if key in known}
        return cls(**kwargs)

    def to_mapping(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class DiagnosticSignalsSpec:
    enabled: bool = False
    statuses: list[str] = field(default_factory=lambda: ["shadow"])
    registry: str = ""

    @classmethod
    def from_mapping(cls, data: Any) -> "DiagnosticSignalsSpec":
        if data is None:
            return cls()
        if isinstance(data, bool):
            return cls(enabled=data)
        if not isinstance(data, dict):
            raise TypeError(f"diagnostic_signals must be a mapping or bool, got {type(data).__name__}")
        statuses = data.get("statuses", ["shadow"])
        if isinstance(statuses, str):
            statuses = [item.strip() for item in statuses.split(",") if item.strip()]
        if not isinstance(statuses, list) or not all(isinstance(item, str) for item in statuses):
            raise TypeError("diagnostic_signals.statuses must be a string or list of strings")
        unknown = sorted(set(statuses) - {"draft", "shadow", "online", "retired"})
        if unknown:
            raise ValueError(f"unknown diagnostic signal statuses: {unknown}")
        return cls(
            enabled=bool(data.get("enabled", False)),
            statuses=list(statuses),
            registry=str(data.get("registry") or ""),
        )

    def to_mapping(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @property
    def statuses_csv(self) -> str:
        return ",".join(self.statuses)


@dataclass(frozen=True)
class HarnessSpec:
    name: str
    task_suite_name: str = "libero_90"
    tasks: list[int] = field(default_factory=list)
    generated_benchmark_dir: str = ""
    generated_split: str = "smoke"
    episodes_per_task: int = 5
    model: str = "pi0_libero_openpi"
    config_name: str = "pi0_libero"
    skills: str = "online"
    skill_pack: str = ""
    skill_index: str = ""
    recovery: bool = True
    save_video: bool = False
    export_annotated: bool = True
    gpus: list[int] = field(default_factory=lambda: [0])
    seed: int = 90
    action_chunk: int = 5
    num_steps_wait: int = 10
    max_recovery_calls: int = 1
    max_recovery_steps: int = 200
    max_replans: int = 1
    policy_in_process: bool = True
    force_recovery_query: int = -1
    num_particles: int = 128
    particle_iters: int = 100
    particle_lr: float = 0.045
    min_success_fraction: float = 0.01
    fps: int = 10
    real_cutamp: RealCutampSpec = field(default_factory=RealCutampSpec)
    diagnostic_signals: DiagnosticSignalsSpec = field(default_factory=DiagnosticSignalsSpec)
    archive_offline_scan_corpus: bool = True
    offline_scan_corpus_root: str = "analysis_outputs/offline_trigger_corpus"
    offline_skill_scan: bool = True
    offline_scan_include_hints: bool = True
    gates: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "HarnessSpec":
        if not isinstance(data, dict):
            raise TypeError("harness spec must be a mapping")
        payload = dict(data)
        if "suite" in payload and "task_suite_name" not in payload:
            payload["task_suite_name"] = payload.pop("suite")
        payload["tasks"] = parse_task_ids(payload.get("tasks"))
        payload["gpus"] = parse_gpu_ids(payload.get("gpus", [0]))
        if "episodes" in payload and "episodes_per_task" not in payload:
            payload["episodes_per_task"] = payload.pop("episodes")
        payload["real_cutamp"] = RealCutampSpec.from_mapping(payload.get("real_cutamp"))
        payload["diagnostic_signals"] = DiagnosticSignalsSpec.from_mapping(payload.get("diagnostic_signals"))
        skills = payload.get("skills", cls.skills)
        if skills not in {"online", "mining", "off"}:
            raise ValueError("skills must be one of: online, mining, off")
        if skills != "off" and not (
            str(payload.get("skill_pack") or "").strip()
            or str(payload.get("skill_index") or "").strip()
        ):
            raise ValueError("skill-enabled harness specs require skill_pack or skill_index")
        if payload.get("generated_split", "smoke") not in {"smoke", "train", "validation", "all"}:
            raise ValueError("generated_split must be one of: smoke, train, validation, all")
        if not payload.get("name"):
            raise ValueError("harness spec requires a name")
        if not payload["tasks"]:
            raise ValueError("harness spec requires at least one task")
        return cls(**payload)

    def to_mapping(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["real_cutamp"] = self.real_cutamp.to_mapping()
        payload["diagnostic_signals"] = self.diagnostic_signals.to_mapping()
        return payload

    @property
    def effective_max_recovery_calls(self) -> int:
        return int(self.max_recovery_calls if self.recovery else 0)

    @property
    def task_id_string(self) -> str:
        return ",".join(str(task) for task in self.tasks)

    def with_overrides(
        self,
        *,
        tasks: Any = None,
        gpus: Any = None,
        model: str | None = None,
        skill_pack: str | None = None,
    ) -> "HarnessSpec":
        payload = self.to_mapping()
        if tasks is not None:
            payload["tasks"] = parse_task_ids(tasks)
        if gpus is not None:
            payload["gpus"] = parse_gpu_ids(gpus)
        if model is not None:
            payload["model"] = model
        if skill_pack is not None:
            payload["skill_pack"] = skill_pack
        return HarnessSpec.from_mapping(payload)


def load_spec(path: str | Path) -> HarnessSpec:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text)
    return HarnessSpec.from_mapping(payload or {})


def dump_spec_json(spec: HarnessSpec, path: str | Path) -> None:
    Path(path).write_text(json.dumps(spec.to_mapping(), ensure_ascii=False, indent=2), encoding="utf-8")
