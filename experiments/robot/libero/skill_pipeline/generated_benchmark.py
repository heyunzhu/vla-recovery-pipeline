"""Generate LIBERO-derived benchmark manifests for skill mining.

The generator treats original LIBERO tasks as scene templates. It rewrites
simple BDDL goals in controlled ways, records provenance back to the source
task, and freezes deterministic train/validation/smoke splits. It deliberately
does not execute rollouts; online smoke/eval remains the job of the harness.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from experiments.robot.libero.tiptop_repro.bddl_goals import parse_bddl_task_goals


DEFAULT_RELATIVE_DIRECTIONS = ("left", "right", "front", "back")
DEFAULT_CADDY_COMPARTMENTS = ("front", "back", "left", "right")
DEFAULT_SUPPORTED_TEMPLATES = (
    "pick_place_on_surface",
    "put_inside_container",
    "caddy_compartment",
)


@dataclass(frozen=True)
class GoalAtom:
    predicate: str
    args: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GoalAtom":
        return cls(
            predicate=str(data.get("predicate") or "").lower(),
            args=tuple(str(arg) for arg in data.get("args") or ()),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {"predicate": self.predicate, "args": list(self.args)}


@dataclass(frozen=True)
class RegionSpec:
    name: str
    target: str = ""
    qualified_name: str = ""
    ranges: tuple[float, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RegionSpec":
        name = str(data.get("name") or "")
        target = str(data.get("target") or "")
        qualified = str(data.get("qualified_name") or (f"{target}_{name}" if target else name))
        return cls(
            name=name,
            target=target,
            qualified_name=qualified,
            ranges=tuple(float(x) for x in data.get("ranges") or ()),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "qualified_name": self.qualified_name,
            "ranges": list(self.ranges),
        }


@dataclass(frozen=True)
class SourceTask:
    """A source LIBERO task and its BDDL inventory."""

    suite: str
    task_id_1based: int
    language: str
    bddl_text: str
    problem_folder: str = ""
    bddl_file: str = ""
    bddl_path: str = ""
    objects: tuple[str, ...] = ()
    fixtures: tuple[str, ...] = ()
    obj_of_interest: tuple[str, ...] = ()
    goal_atoms: tuple[GoalAtom, ...] = ()
    regions: tuple[RegionSpec, ...] = ()

    @classmethod
    def from_bddl(
        cls,
        *,
        suite: str,
        task_id_1based: int,
        bddl_text: str,
        language: str | None = None,
        problem_folder: str = "",
        bddl_file: str = "",
        bddl_path: str = "",
    ) -> "SourceTask":
        parsed = parse_bddl_task_goals(bddl_text)
        region_by_name = dict(parsed.get("regions") or {})
        unique_regions = _dedupe_regions(region_by_name.values())
        parsed_language = str(parsed.get("language") or "").strip()
        return cls(
            suite=suite,
            task_id_1based=int(task_id_1based),
            language=str(language or parsed_language),
            bddl_text=bddl_text,
            problem_folder=problem_folder,
            bddl_file=bddl_file,
            bddl_path=bddl_path,
            objects=tuple(_parse_typed_section_names(bddl_text, "objects")),
            fixtures=tuple(_parse_typed_section_names(bddl_text, "fixtures")),
            obj_of_interest=tuple(str(x) for x in parsed.get("obj_of_interest") or ()),
            goal_atoms=tuple(GoalAtom.from_mapping(x) for x in parsed.get("goal_atoms") or ()),
            regions=tuple(RegionSpec.from_mapping(x) for x in unique_regions),
        )

    @property
    def scene_names(self) -> tuple[str, ...]:
        return _dedupe([*self.objects, *self.fixtures])

    def to_mapping(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "task_id_1based": self.task_id_1based,
            "language": self.language,
            "problem_folder": self.problem_folder,
            "bddl_file": self.bddl_file,
            "bddl_path": self.bddl_path,
            "objects": list(self.objects),
            "fixtures": list(self.fixtures),
            "obj_of_interest": list(self.obj_of_interest),
            "goal_atoms": [atom.to_mapping() for atom in self.goal_atoms],
            "regions": [region.to_mapping() for region in self.regions],
            "skill_tags": infer_skill_tags(self),
        }


@dataclass(frozen=True)
class GeneratedTask:
    """A generated task spec with a rewritten BDDL problem."""

    task_id: str
    split: str
    template: str
    language: str
    bddl_text: str
    source_suite: str
    source_task_id_1based: int
    source_language: str
    goal_atoms: tuple[GoalAtom, ...]
    obj_of_interest: tuple[str, ...]
    tags: tuple[str, ...]
    notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self, *, include_bddl_text: bool = False) -> dict[str, Any]:
        payload = {
            "task_id": self.task_id,
            "split": self.split,
            "template": self.template,
            "language": self.language,
            "source_suite": self.source_suite,
            "source_task_id_1based": self.source_task_id_1based,
            "source_language": self.source_language,
            "goal_atoms": [atom.to_mapping() for atom in self.goal_atoms],
            "obj_of_interest": list(self.obj_of_interest),
            "tags": list(self.tags),
            "notes": list(self.notes),
            "metadata": dict(self.metadata),
            "bddl_file": f"{self.task_id}.bddl",
        }
        if include_bddl_text:
            payload["bddl_text"] = self.bddl_text
        return payload

    def with_split(self, split: str) -> "GeneratedTask":
        return dataclasses.replace(self, split=split)


@dataclass(frozen=True)
class GenerationConfig:
    source_suite: str = "libero_90"
    templates: tuple[str, ...] = DEFAULT_SUPPORTED_TEMPLATES
    seed: int = 42
    max_candidates_per_source: int = 12
    train_limit: int = 300
    validation_limit: int = 50
    smoke_per_template: int = 1
    validation_fraction: float = 0.15
    canonical_episodes_per_task: int = 5
    include_multi_goal_sources: bool = False
    include_relative_regions: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None = None) -> "GenerationConfig":
        if data is None:
            return cls()
        payload = dict(data)
        if "templates" in payload and isinstance(payload["templates"], list):
            payload["templates"] = tuple(str(x) for x in payload["templates"])
        return cls(**payload)

    def to_mapping(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["templates"] = list(self.templates)
        return payload


def inventory_from_libero(suite: str = "libero_90") -> list[SourceTask]:
    """Read source tasks from an installed LIBERO benchmark package."""

    try:
        from libero.libero import benchmark, get_libero_path
    except Exception as exc:  # pragma: no cover - depends on remote LIBERO env.
        raise RuntimeError(
            "LIBERO is not importable. Run this generator in the evaluation environment "
            "or pass prebuilt SourceTask objects in tests."
        ) from exc

    task_suite = benchmark.get_benchmark_dict()[suite]()
    bddl_root = Path(get_libero_path("bddl_files"))
    tasks: list[SourceTask] = []
    for task_idx in range(task_suite.n_tasks):
        task = task_suite.get_task(task_idx)
        bddl_path = bddl_root / task.problem_folder / task.bddl_file
        bddl_text = bddl_path.read_text(encoding="utf-8")
        tasks.append(
            SourceTask.from_bddl(
                suite=suite,
                task_id_1based=task_idx + 1,
                language=str(task.language),
                bddl_text=bddl_text,
                problem_folder=str(task.problem_folder),
                bddl_file=str(task.bddl_file),
                bddl_path=str(bddl_path),
            )
        )
    return tasks


def generate_candidates(
    sources: Sequence[SourceTask],
    config: GenerationConfig | None = None,
) -> list[GeneratedTask]:
    cfg = config or GenerationConfig()
    enabled = set(cfg.templates)
    candidates: list[GeneratedTask] = []
    for source in sources:
        if not cfg.include_multi_goal_sources and len(_placement_atoms(source)) != 1:
            continue
        per_source: list[GeneratedTask] = []
        if "pick_place_on_surface" in enabled:
            per_source.extend(_surface_variants(source))
        if "put_inside_container" in enabled:
            per_source.extend(_inside_variants(source))
        if "caddy_compartment" in enabled:
            per_source.extend(_caddy_compartment_variants(source))
        if cfg.include_relative_regions and "relative_place" in enabled:
            per_source.extend(_relative_region_variants(source))
        candidates.extend(per_source[: cfg.max_candidates_per_source])
    return _dedupe_candidates(candidates)


def split_candidates(
    candidates: Sequence[GeneratedTask],
    config: GenerationConfig | None = None,
) -> dict[str, list[GeneratedTask]]:
    cfg = config or GenerationConfig()
    rng = random.Random(cfg.seed)
    groups: dict[str, list[GeneratedTask]] = defaultdict(list)
    for item in candidates:
        groups[item.template].append(item)
    for items in groups.values():
        items.sort(key=lambda task: task.task_id)
        rng.shuffle(items)

    smoke: list[GeneratedTask] = []
    validation: list[GeneratedTask] = []
    train: list[GeneratedTask] = []

    for template in sorted(groups):
        items = groups[template]
        smoke_count = min(cfg.smoke_per_template, len(items))
        smoke.extend(item.with_split("smoke") for item in items[:smoke_count])
        rest = items[smoke_count:]
        if not rest:
            continue
        target_validation = max(1, round(len(rest) * cfg.validation_fraction))
        target_validation = min(target_validation, max(0, cfg.validation_limit - len(validation)))
        validation.extend(item.with_split("validation") for item in rest[:target_validation])
        train.extend(item.with_split("train") for item in rest[target_validation:])

    return {
        "smoke": sorted(smoke, key=lambda task: task.task_id),
        "validation": sorted(validation[: cfg.validation_limit], key=lambda task: task.task_id),
        "train": sorted(train[: cfg.train_limit], key=lambda task: task.task_id),
    }


def write_generated_benchmark(
    out_dir: str | Path,
    *,
    sources: Sequence[SourceTask],
    splits: Mapping[str, Sequence[GeneratedTask]],
    config: GenerationConfig | None = None,
) -> dict[str, Any]:
    cfg = config or GenerationConfig()
    root = Path(out_dir)
    manifests = root / "manifests"
    inventory_dir = root / "inventory"
    task_specs = root / "task_specs"
    seeds_dir = root / "seeds"
    for path in (manifests, inventory_dir, task_specs, seeds_dir):
        path.mkdir(parents=True, exist_ok=True)

    _write_jsonl(inventory_dir / f"{cfg.source_suite}_tasks.jsonl", [source.to_mapping() for source in sources])

    all_tasks: list[GeneratedTask] = []
    for split, tasks in sorted(splits.items()):
        split_dir = task_specs / split
        split_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for task in sorted(tasks, key=lambda item: item.task_id):
            (split_dir / f"{task.task_id}.bddl").write_text(task.bddl_text, encoding="utf-8")
            row = task.to_mapping()
            row["bddl_path"] = str((split_dir / f"{task.task_id}.bddl").relative_to(root)).replace("\\", "/")
            rows.append(row)
            all_tasks.append(task)
        _write_jsonl(manifests / f"{split}_tasks.jsonl", rows)

    all_rows = []
    for task in sorted(all_tasks, key=lambda item: (item.split, item.task_id)):
        row = task.to_mapping()
        row["bddl_path"] = f"task_specs/{task.split}/{task.task_id}.bddl"
        all_rows.append(row)
    _write_jsonl(manifests / "all_tasks.jsonl", all_rows)

    canonical = {
        "schema_version": 1,
        "seed": cfg.seed,
        "episodes_per_task": cfg.canonical_episodes_per_task,
        "episodes": [
            {
                "task_id": task.task_id,
                "split": task.split,
                "source_suite": task.source_suite,
                "source_task_id_1based": task.source_task_id_1based,
                "episode_indices": list(range(cfg.canonical_episodes_per_task)),
            }
            for task in sorted(all_tasks, key=lambda item: (item.split, item.task_id))
        ],
    }
    (seeds_dir / "canonical_episodes.json").write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": cfg.to_mapping(),
        "source_tasks": len(sources),
        "generated_tasks": len(all_tasks),
        "splits": {split: len(tasks) for split, tasks in sorted(splits.items())},
        "templates": _count_by(all_tasks, lambda task: task.template),
        "tags": _count_tags(all_tasks),
    }
    (root / "benchmark_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "README.md").write_text(_render_readme(summary), encoding="utf-8")
    return summary


def infer_skill_tags(source: SourceTask | GeneratedTask) -> list[str]:
    atoms = list(source.goal_atoms)
    names = list(getattr(source, "obj_of_interest", ()))
    text = " ".join([getattr(source, "language", ""), *names, *[" ".join(atom.args) for atom in atoms]]).lower()
    tags: set[str] = set()
    if any(family in text for family in ("bowl", "mug", "cream_cheese", "butter", "milk", "juice", "book", "moka")):
        tags.add("grasp")
    if any(atom.predicate in {"on", "inside", "in"} for atom in atoms):
        tags.add("grounding")
        tags.add("place")
    if any(word in text for word in ("contain_region", "compartment", "drawer", "cabinet", "basket", "bowl", "rack")):
        tags.add("geometry")
    if any(word in text for word in ("drawer", "microwave", "cabinet")):
        tags.add("repair")
    return sorted(tags)


def _surface_variants(source: SourceTask) -> list[GeneratedTask]:
    objects = _movable_objects(source)
    target_candidates = [name for name in source.scene_names if _is_direct_surface_target(name)]
    if not objects or not target_candidates:
        return []
    out: list[GeneratedTask] = []
    for obj in objects:
        for target in target_candidates:
            if _same_entity(obj, target):
                continue
            language = f"pick up the {_label(obj)} and place it on the {_label(target)}"
            out.append(
                _make_generated_task(
                    source,
                    template="pick_place_on_surface",
                    obj=obj,
                    target=target,
                    predicate="On",
                    language=language,
                    notes=("surface target substituted within the source scene",),
                )
            )
    return out


def _inside_variants(source: SourceTask) -> list[GeneratedTask]:
    object_candidates = _movable_objects(source)
    container_candidates = _container_targets(source)
    if not object_candidates or not container_candidates:
        return []
    out: list[GeneratedTask] = []
    for obj in object_candidates:
        for target in container_candidates:
            if _same_entity(obj, target) or _same_language_label(obj, target):
                continue
            language = f"pick up the {_label(obj)} and place it in the {_label(target)}"
            out.append(
                _make_generated_task(
                    source,
                    template="put_inside_container",
                    obj=obj,
                    target=target,
                    predicate="In",
                    language=language,
                    notes=("inside/container target substituted within the source scene",),
                )
            )
    return out


def _caddy_compartment_variants(source: SourceTask) -> list[GeneratedTask]:
    caddies = [name for name in source.fixtures + source.objects if "caddy" in name.lower()]
    if not caddies:
        return []
    movable = [
        name
        for name in source.objects
        if classify_object(name) in {"book", "mug", "flat_box", "carton", "bottle_or_can"}
    ]
    if not movable:
        return []
    caddy = caddies[0]
    out: list[GeneratedTask] = []
    for obj in movable:
        for compartment in DEFAULT_CADDY_COMPARTMENTS:
            target = f"{caddy}_{compartment}_contain_region"
            language = f"pick up the {_label(obj)} and place it in the {compartment} compartment of the caddy"
            notes = (
                "synthetic caddy compartment region",
                "requires smoke validation because compartment geometry is task-specific",
            )
            out.append(
                _make_generated_task(
                    source,
                    template="caddy_compartment",
                    obj=obj,
                    target=target,
                    predicate="In",
                    language=language,
                    notes=notes,
                    extra_regions=((f"{compartment}_contain_region", caddy),),
                    metadata={"compartment": compartment, "container": caddy},
                )
            )
    return out


def _relative_region_variants(source: SourceTask) -> list[GeneratedTask]:
    objects = _movable_objects(source)
    anchors = [name for name in source.objects if classify_target(name) in {"surface", "container"}]
    tables = [name for name in source.fixtures if "table" in name.lower()] or [name for name in source.scene_names if "table" in name.lower()]
    if not objects or not anchors or not tables:
        return []
    table = tables[0]
    out: list[GeneratedTask] = []
    for obj in objects:
        for anchor in anchors:
            if _same_entity(obj, anchor):
                continue
            for direction in DEFAULT_RELATIVE_DIRECTIONS:
                region = f"{table}_{anchor}_{direction}_region"
                language = f"pick up the {_label(obj)} and place it to the {direction} of the {_label(anchor)}"
                out.append(
                    _make_generated_task(
                        source,
                        template="relative_place",
                        obj=obj,
                        target=region,
                        predicate="On",
                        language=language,
                        notes=("synthetic relative region; requires geometry authoring before online use",),
                        extra_regions=((f"{anchor}_{direction}_region", table),),
                        metadata={"anchor": anchor, "direction": direction, "region_target": table},
                    )
                )
    return out


def classify_object(name: str) -> str:
    low = name.lower()
    if "bowl" in low:
        return "bowl"
    if "mug" in low or "cup" in low:
        return "mug"
    if "book" in low:
        return "book"
    if "moka" in low:
        return "moka_pot"
    if "milk" in low or "juice" in low or "carton" in low:
        return "carton"
    if "cream_cheese" in low or "butter" in low or "box" in low:
        return "flat_box"
    if any(word in low for word in ("soup", "sauce", "ketchup", "dressing", "pudding")):
        return "bottle_or_can"
    return "unknown"


def classify_target(name: str) -> str:
    low = name.lower()
    if "contain_region" in low or any(word in low for word in ("basket", "drawer", "microwave")):
        return "container"
    if any(word in low for word in ("left_region", "right_region", "front_region", "back_region")):
        return "relative_region"
    if any(word in low for word in ("plate", "stove", "table", "counter", "cabinet_top", "top_side", "rack")):
        return "surface"
    if "bowl" in low or "caddy" in low:
        return "container"
    return "unknown"


def _is_direct_surface_target(name: str) -> bool:
    low = name.lower()
    if any(word in low for word in ("table", "counter")):
        return False
    return classify_target(name) == "surface"


def _make_generated_task(
    source: SourceTask,
    *,
    template: str,
    obj: str,
    target: str,
    predicate: str,
    language: str,
    notes: Sequence[str] = (),
    extra_regions: Sequence[tuple[str, str]] = (),
    metadata: Mapping[str, Any] | None = None,
) -> GeneratedTask:
    task_id = _generated_id(source, template, obj, target)
    goal = GoalAtom(predicate=predicate.lower() if predicate.lower() != "in" else "inside", args=(obj, target))
    bddl_text = rewrite_bddl(
        source.bddl_text,
        problem_name=task_id,
        language=language,
        obj_of_interest=(obj, _interest_target(target)),
        goal_predicate=predicate,
        goal_args=(obj, target),
        extra_regions=extra_regions,
    )
    draft = GeneratedTask(
        task_id=task_id,
        split="unassigned",
        template=template,
        language=language,
        bddl_text=bddl_text,
        source_suite=source.suite,
        source_task_id_1based=source.task_id_1based,
        source_language=source.language,
        goal_atoms=(goal,),
        obj_of_interest=(obj, _interest_target(target)),
        tags=(),
        notes=tuple(notes),
        metadata=metadata or {},
    )
    return dataclasses.replace(draft, tags=tuple(infer_skill_tags(draft)))


def rewrite_bddl(
    text: str,
    *,
    problem_name: str,
    language: str,
    obj_of_interest: Sequence[str],
    goal_predicate: str,
    goal_args: Sequence[str],
    extra_regions: Sequence[tuple[str, str]] = (),
) -> str:
    # LIBERO dispatches env classes from the BDDL problem name. Keep the source
    # domain name stable; the generated task identity lives in the filename and manifest.
    _ = problem_name
    out = text
    out = _replace_section(out, "language", " " + language)
    interest_body = "\n    " + "\n    ".join(obj_of_interest) + "\n  "
    out = _replace_section(out, "obj_of_interest", interest_body)
    pred = "in" if goal_predicate.lower() in {"in", "inside"} else goal_predicate.lower()
    goal_body = f"\n    (And ({pred} {' '.join(goal_args)}))\n  "
    out = _replace_section(out, "goal", goal_body)
    for region_name, target in extra_regions:
        out = _ensure_region(out, region_name, target)
    return out


def _placement_atoms(source: SourceTask) -> list[GoalAtom]:
    return [atom for atom in source.goal_atoms if atom.predicate in {"on", "inside", "in"}]


def _single_atom(source: SourceTask, predicates: set[str]) -> GoalAtom | None:
    atoms = [atom for atom in _placement_atoms(source) if atom.predicate in predicates]
    return atoms[0] if len(atoms) == 1 else None


def _container_targets(source: SourceTask) -> list[str]:
    targets: list[str] = []
    for name in source.scene_names:
        if classify_target(name) == "container":
            if not name.endswith("_contain_region") and any(word in name.lower() for word in ("basket", "bowl", "caddy")):
                targets.append(f"{name}_contain_region")
            else:
                targets.append(name)
    for region in source.regions:
        if "contain_region" in region.qualified_name.lower():
            targets.append(region.qualified_name)
    return _dedupe(targets)


def _movable_objects(source: SourceTask) -> list[str]:
    return [name for name in source.objects if classify_object(name) != "unknown"]


def _entity_root(name: str) -> str:
    root = _interest_target(name)
    root = re.sub(r"_(main|top_side|cabinet_top|cabinet_middle|cabinet_bottom)$", "", root)
    root = re.sub(r"_(left|right|front|back)_(?:contain_)?region$", "", root)
    return root


def _same_entity(lhs: str, rhs: str) -> bool:
    return _entity_root(lhs) == _entity_root(rhs)


def _same_language_label(lhs: str, rhs: str) -> bool:
    return _label(lhs).lower() == _label(rhs).lower()


def _interest_target(target: str) -> str:
    for suffix in ("_front_contain_region", "_back_contain_region", "_left_contain_region", "_right_contain_region", "_contain_region"):
        if target.endswith(suffix):
            return target[: -len(suffix)]
    return target


def _label(name: str) -> str:
    raw = _interest_target(name)
    raw = re.sub(r"_\d+(?:_|$)", " ", raw)
    raw = raw.replace("_main", "")
    raw = raw.replace("_", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw or name


def _generated_id(source: SourceTask, template: str, obj: str, target: str) -> str:
    digest = hashlib.sha1(f"{source.suite}:{source.task_id_1based}:{template}:{obj}:{target}".encode("utf-8")).hexdigest()
    return f"{source.suite}_gen_t{source.task_id_1based:03d}_{template}_{digest[:8]}"


def _dedupe_candidates(candidates: Sequence[GeneratedTask]) -> list[GeneratedTask]:
    seen: set[tuple[str, int, str, str]] = set()
    out: list[GeneratedTask] = []
    for candidate in candidates:
        key = (
            candidate.source_suite,
            candidate.source_task_id_1based,
            candidate.template,
            candidate.language.lower(),
        )
        if key in seen or candidate.language.lower() == candidate.source_language.lower():
            continue
        seen.add(key)
        out.append(candidate)
    return sorted(out, key=lambda task: task.task_id)


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return tuple(out)


def _dedupe_regions(items: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: set[str] = set()
    out: list[Mapping[str, Any]] = []
    for item in items:
        key = str(item.get("qualified_name") or item.get("name") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _matching_paren(text: str, open_idx: int) -> int:
    depth = 0
    for idx in range(open_idx, len(text)):
        char = text[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _section_span(text: str, heading: str) -> tuple[int, int, int] | None:
    needle = f"(:{heading}"
    start = text.lower().find(needle.lower())
    if start < 0:
        return None
    end = _matching_paren(text, start)
    if end < 0:
        return None
    body_start = start + len(needle)
    return start, body_start, end


def _section_body(text: str, heading: str) -> str:
    span = _section_span(text, heading)
    if span is None:
        return ""
    _, body_start, end = span
    return text[body_start:end].strip()


def _replace_section(text: str, heading: str, body: str) -> str:
    span = _section_span(text, heading)
    if span is None:
        insertion = f"\n  (:{heading}{body})"
        final = text.rfind(")")
        if final < 0:
            return text + insertion + "\n"
        return text[:final] + insertion + "\n" + text[final:]
    start, _, end = span
    return text[:start] + f"(:{heading}{body})" + text[end + 1 :]


def _ensure_region(text: str, region_name: str, target: str) -> str:
    if re.search(rf"\(\s*{re.escape(region_name)}\b", _section_body(text, "regions")):
        return text
    region_form = f"\n    ({region_name}\n      (:target {target})\n    )"
    span = _section_span(text, "regions")
    if span is None:
        body = region_form + "\n  "
        return _replace_section(text, "regions", body)
    start, body_start, end = span
    return text[:end] + region_form + text[end:]


def _parse_typed_section_names(text: str, heading: str) -> list[str]:
    body = _section_body(text, heading)
    if not body:
        return []
    tokens = [tok for tok in re.split(r"[\s()]+", body) if tok]
    names: list[str] = []
    pending: list[str] = []
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if tok == "-":
            names.extend(pending)
            pending = []
            idx += 2
            continue
        pending.append(tok)
        idx += 1
    names.extend(pending)
    return [name for name in names if not name.startswith(":") and name != "-"]


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _count_by(tasks: Iterable[GeneratedTask], key_fn) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for task in tasks:
        counts[str(key_fn(task))] += 1
    return dict(sorted(counts.items()))


def _count_tags(tasks: Iterable[GeneratedTask]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for task in tasks:
        for tag in task.tags:
            counts[tag] += 1
    return dict(sorted(counts.items()))


def _render_readme(summary: Mapping[str, Any]) -> str:
    split_lines = "\n".join(f"- `{name}`: {count}" for name, count in summary.get("splits", {}).items())
    template_lines = "\n".join(f"- `{name}`: {count}" for name, count in summary.get("templates", {}).items())
    return f"""# Generated LIBERO Skill Benchmark

This directory was generated from source LIBERO BDDL tasks. It is intended for
skill-mining and harness validation, not as a replacement for the original
LIBERO benchmark.

## Summary

- source tasks: {summary.get("source_tasks", 0)}
- generated tasks: {summary.get("generated_tasks", 0)}

## Splits

{split_lines or "- none"}

## Templates

{template_lines or "- none"}

## Files

- `inventory/`: parsed source task inventory.
- `task_specs/<split>/*.bddl`: generated BDDL task specs.
- `manifests/*_tasks.jsonl`: generated task metadata and provenance.
- `seeds/canonical_episodes.json`: deterministic source episode mapping for smoke/eval.
"""
