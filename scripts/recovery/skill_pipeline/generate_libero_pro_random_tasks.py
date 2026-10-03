#!/usr/bin/env python3
"""Sample random LIBERO-Pro task variants from existing tabletop scenes.

Each variant changes exactly one of: goal, placement, or geometry.
Placement and geometry edits are written into the BDDL. Their init-state
files are not resampled here, and the simulator is not started.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path


SOURCE_SUITES = (
    "libero_90",
    "libero_goal",
    "libero_spatial",
    "libero_object",
    "libero_10",
)
EDIT_KINDS = ("goal", "placement", "geometry")
TABLE_LIMIT = 0.48
SHIFT_CANDIDATES = (
    (0.08, 0.0),
    (-0.08, 0.0),
    (0.0, 0.08),
    (0.0, -0.08),
    (0.06, 0.06),
    (-0.06, 0.06),
    (0.06, -0.06),
    (-0.06, -0.06),
)
YAW_CHOICES = (0.0, 1.5707963267948966, 3.141592653589793, -1.5707963267948966)


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
    raise ValueError("unbalanced parentheses")


def _section_span(text: str, heading: str) -> tuple[int, int, str]:
    needle = f"(:{heading}"
    start = text.lower().find(needle.lower())
    if start < 0:
        raise ValueError(f"missing (:{heading}")
    end = _matching_paren(text, start)
    body = text[start + len(needle) : end]
    return start, end, body


def _replace_section(text: str, heading: str, body: str) -> str:
    start, end, _old = _section_span(text, heading)
    needle = f"(:{heading}"
    return text[: start + len(needle)] + body + text[end:]


def _forms(body: str) -> list[str]:
    forms: list[str] = []
    idx = 0
    while True:
        open_idx = body.find("(", idx)
        if open_idx < 0:
            break
        close_idx = _matching_paren(body, open_idx)
        forms.append(body[open_idx : close_idx + 1])
        idx = close_idx + 1
    return forms


def _label(name: str) -> str:
    base = name.strip()
    if re.search(r"_\d+$", base):
        base = base.rsplit("_", 1)[0]
    return base.replace("_", " ")


def _round_floats(values: list[float], digits: int = 3) -> tuple[float, ...]:
    return tuple(round(value, digits) for value in values)


def _parse_pairs(body: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in body.splitlines():
        match = re.search(r"([A-Za-z0-9_]+)\s*-\s*([A-Za-z0-9_]+)", line)
        if match:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def _parse_atoms(body: str) -> list[tuple[str, tuple[str, ...]]]:
    atoms: list[tuple[str, tuple[str, ...]]] = []
    for form in _forms(body):
        tokens = form.replace("(", " ").replace(")", " ").split()
        if not tokens:
            continue
        if tokens[0].lower() == "and":
            tokens = tokens[1:]
        if len(tokens) < 2:
            continue
        atoms.append((tokens[0], tuple(tokens[1:])))
    return atoms


def _parse_regions(body: str) -> list[dict]:
    regions: list[dict] = []
    for form in _forms(body):
        close_name = form.find(")")
        # Region forms are (name (:target ...) (:ranges ...)).
        head = form[1:close_name] if close_name > 0 else ""
        name = head.split()[0] if head.split() else ""
        if not name or name.startswith(":"):
            continue
        target_match = re.search(r"\(:target\s+([A-Za-z0-9_]+)\s*\)", form)
        range_match = re.search(r"\(:ranges\s*\((.*?)\)\s*\)", form, flags=re.S)
        yaw_match = re.search(r"\(:yaw_rotation\s*\((.*?)\)\s*\)", form, flags=re.S)
        ranges = [float(token) for token in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", range_match.group(1))] if range_match else []
        yaws = [float(token) for token in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", yaw_match.group(1))] if yaw_match else []
        regions.append(
            {
                "name": name,
                "target": target_match.group(1) if target_match else "",
                "ranges": ranges,
                "yaws": yaws,
                "form": form,
            }
        )
    return regions


def parse_scene(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    _ls, _le, language_body = _section_span(text, "language")
    _is, _ie, interest_body = _section_span(text, "obj_of_interest")
    _gs, _ge, goal_body = _section_span(text, "goal")
    _fs, _fe, fixture_body = _section_span(text, "fixtures")
    _os, _oe, object_body = _section_span(text, "objects")
    _rs, _re, region_body = _section_span(text, "regions")
    _ns, _ne, init_body = _section_span(text, "init")
    goal_atoms = _parse_atoms(goal_body)
    init_atoms = _parse_atoms(init_body)
    placement = next((atom for atom in goal_atoms if atom[0].lower() in {"on", "in", "inside"} and len(atom[1]) >= 2), None)
    regions = _parse_regions(region_body)
    return {
        "path": path,
        "text": text,
        "language": " ".join(language_body.split()),
        "interest": re.findall(r"[A-Za-z0-9_]+", interest_body),
        "goal_atoms": goal_atoms,
        "placement": placement,
        "init_atoms": init_atoms,
        "fixtures": _parse_pairs(fixture_body),
        "objects": _parse_pairs(object_body),
        "regions": regions,
        "object_regions": _object_regions(regions, init_atoms),
    }


def _qualified_region_name(region: dict) -> str:
    target = region["target"]
    name = region["name"]
    if target and not name.startswith(f"{target}_"):
        return f"{target}_{name}"
    return name


def _object_regions(regions: list[dict], init_atoms: list[tuple[str, tuple[str, ...]]]) -> dict[str, dict]:
    by_qualified = {_qualified_region_name(region): region for region in regions}
    found: dict[str, dict] = {}
    for predicate, args in init_atoms:
        if predicate.lower() != "on" or len(args) < 2:
            continue
        region = by_qualified.get(args[1])
        if region is None or len(region.get("ranges") or []) < 4:
            continue
        found[args[0]] = region
    return found


def scene_key(scene: dict) -> tuple:
    fixtures = tuple(sorted(kind for _name, kind in scene["fixtures"]))
    objects = tuple(sorted(kind for _name, kind in scene["objects"]))
    regions = tuple(
        sorted(
            (
                region["name"],
                region["target"],
                _round_floats(region["ranges"]),
                _round_floats(region["yaws"]),
            )
            for region in scene["regions"]
        )
    )
    return fixtures, objects, regions


def _object_region(scene: dict, instance: str) -> dict | None:
    return scene.get("object_regions", {}).get(instance)


def _range_box(ranges: list[float]) -> tuple[float, float, float, float] | None:
    if len(ranges) < 4:
        return None
    x1, y1, x2, y2 = ranges[:4]
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _shifted_ranges(ranges: list[float], dx: float, dy: float) -> list[float] | None:
    box = _range_box(ranges)
    if box is None:
        return None
    x1, y1, x2, y2 = box
    nx1, ny1, nx2, ny2 = x1 + dx, y1 + dy, x2 + dx, y2 + dy
    if min(nx1, nx2) < -TABLE_LIMIT or max(nx1, nx2) > TABLE_LIMIT:
        return None
    if min(ny1, ny2) < -TABLE_LIMIT or max(ny1, ny2) > TABLE_LIMIT:
        return None
    return [nx1, ny1, nx2, ny2]


def _center(ranges: list[float]) -> tuple[float, float] | None:
    box = _range_box(ranges)
    if box is None:
        return None
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2, (y1 + y2) / 2


def _overlaps(ranges: list[float], others: list[list[float]], gap: float = 0.03) -> bool:
    center = _center(ranges)
    if center is None:
        return True
    for other in others:
        other_center = _center(other)
        if other_center is None:
            continue
        if abs(center[0] - other_center[0]) < gap and abs(center[1] - other_center[1]) < gap:
            return True
    return False


def _replace_region_form(text: str, old_form: str, new_form: str) -> str:
    start, end, body = _section_span(text, "regions")
    if old_form not in body:
        raise ValueError("region form not found")
    body = body.replace(old_form, new_form, 1)
    needle = "(:regions"
    return text[: start + len(needle)] + body + text[end:]


def _format_ranges(ranges: list[float]) -> str:
    return " ".join(f"{value:.4f}" for value in ranges[:4])


def _replace_balanced(text: str, keyword: str, replacement: str) -> str:
    marker = f"(:{keyword}"
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"missing (:{keyword}")
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[:start] + replacement + text[index + 1 :]
    raise ValueError(f"unbalanced (:{keyword}")


def _rewrite_region_ranges(form: str, ranges: list[float]) -> str:
    replacement = f"(:ranges (\n              ({_format_ranges(ranges)})\n            )\n          )"
    return _replace_balanced(form, "ranges", replacement)


def _rewrite_region_yaw(form: str, yaw: float) -> str:
    block = f"(:yaw_rotation (\n              ({yaw:.6f} {yaw:.6f})\n            )\n          )"
    if "(:yaw_rotation" in form:
        return _replace_balanced(form, "yaw_rotation", block)
    close = form.rfind(")")
    return form[:close] + "\n      " + block + form[close:]


def _goal_predicate(name: str, kind: str) -> str:
    text = f"{name} {kind}"
    if "basket" in text or "microwave" in text:
        return "In"
    return "On"


def _goal_targets(scene: dict) -> list[tuple[str, str]]:
    current = scene["placement"][1][1] if scene["placement"] else ""
    subject = scene["placement"][1][0] if scene["placement"] else ""
    targets: list[tuple[str, str]] = []
    for name, kind in scene["objects"]:
        if name in {subject, current}:
            continue
        targets.append((name, _goal_predicate(name, kind)))
    for name, kind in scene["fixtures"]:
        if kind in {"table", "main_table", "living_room_table"} or name == current:
            continue
        targets.append((name, _goal_predicate(name, kind)))
    return targets


def apply_goal(scene: dict, rng: random.Random) -> tuple[str, dict] | None:
    if not scene["objects"]:
        return None
    subject = scene["placement"][1][0] if scene["placement"] else scene["objects"][0][0]
    targets = _goal_targets(scene)
    if not targets:
        return None
    rng.shuffle(targets)
    target, predicate = targets[0]
    relation = "in" if predicate == "In" else "on"
    language = f"put the {_label(subject)} {relation} the {_label(target)}"
    text = _replace_section(scene["text"], "language", " " + language)
    text = _replace_section(text, "obj_of_interest", f"\n    {subject}\n    {target}\n  ")
    text = _replace_section(text, "goal", f"\n    (And ({predicate} {subject} {target}))\n  ")
    detail = {
        "subject": subject,
        "target": target,
        "predicate": predicate,
        "language": language,
    }
    return text, detail


def _movable_region(scene: dict, rng: random.Random) -> dict | None:
    subject = scene["placement"][1][0] if scene["placement"] else ""
    preferred = _object_region(scene, subject) if subject else None
    if preferred is not None:
        return preferred
    found = [region for name, _kind in scene["objects"] if (region := _object_region(scene, name))]
    if not found:
        found = list(scene.get("object_regions", {}).values())
    if not found:
        return None
    return rng.choice(found)


def apply_placement(scene: dict, rng: random.Random) -> tuple[str, dict] | None:
    region = _movable_region(scene, rng)
    if region is None:
        return None
    others = [other["ranges"] for other in scene["regions"] if other is not region and other["ranges"]]
    shifts = list(SHIFT_CANDIDATES)
    rng.shuffle(shifts)
    for dx, dy in shifts:
        shifted = _shifted_ranges(region["ranges"], dx, dy)
        if shifted is None or _overlaps(shifted, others):
            continue
        new_form = _rewrite_region_ranges(region["form"], shifted)
        text = _replace_region_form(scene["text"], region["form"], new_form)
        return text, {
            "region": region["name"],
            "from_ranges": [round(value, 4) for value in region["ranges"][:4]],
            "to_ranges": [round(value, 4) for value in shifted],
            "shift_m": [dx, dy],
            "init_resample_required": True,
        }
    return None


def apply_geometry(scene: dict, rng: random.Random) -> tuple[str, dict] | None:
    region = _movable_region(scene, rng)
    if region is None:
        return None
    current = region["yaws"][0] if region["yaws"] else None
    choices = [yaw for yaw in YAW_CHOICES if current is None or abs(yaw - current) > 0.2]
    if not choices:
        return None
    yaw = rng.choice(choices)
    new_form = _rewrite_region_yaw(region["form"], yaw)
    text = _replace_region_form(scene["text"], region["form"], new_form)
    return text, {
        "region": region["name"],
        "from_yaw": None if current is None else round(current, 4),
        "to_yaw": round(yaw, 4),
        "init_resample_required": True,
    }


def collect_scenes(bddl_root: Path, suites: tuple[str, ...]) -> list[dict]:
    unique: dict[tuple, dict] = {}
    for suite in suites:
        suite_dir = bddl_root / suite
        if not suite_dir.is_dir():
            continue
        for path in sorted(suite_dir.glob("*.bddl")):
            scene = parse_scene(path)
            scene["suite"] = suite
            key = scene_key(scene)
            unique.setdefault(key, scene)
    return list(unique.values())


def generate(scenes: list[dict], rng: random.Random, max_tasks: int) -> list[dict]:
    order = list(scenes)
    rng.shuffle(order)
    per_kind = max(1, max_tasks // len(EDIT_KINDS))
    rows: list[dict] = []
    used: set[tuple] = set()
    for kind in EDIT_KINDS:
        produced = 0
        for scene in order:
            if produced >= per_kind or len(rows) >= max_tasks:
                break
            key = scene_key(scene)
            if key in used:
                continue
            applied = {"goal": apply_goal, "placement": apply_placement, "geometry": apply_geometry}[kind](scene, rng)
            if applied is None:
                continue
            text, detail = applied
            if text.count("(") != text.count(")"):
                continue
            used.add(key)
            digest = hashlib.sha1(f"{scene['path']}:{kind}:{json.dumps(detail, sort_keys=True)}".encode()).hexdigest()[:8]
            task_id = f"{scene['suite']}_{scene['path'].stem}_{kind}_{digest}"
            rows.append(
                {
                    "task_id": task_id,
                    "edit": kind,
                    "source_suite": scene["suite"],
                    "source_bddl": str(scene["path"]),
                    "source_language": scene["language"],
                    "new_language": detail.get("language", scene["language"]),
                    "detail": detail,
                    "bddl_text": text,
                }
            )
            produced += 1
    return rows


def write_output(rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.jsonl"
    with manifest.open("w", encoding="utf-8") as handle:
        for row in rows:
            text = row.pop("bddl_text")
            task_path = out_dir / "bddl" / row["edit"] / f"{row['task_id']}.bddl"
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(text, encoding="utf-8")
            row["bddl_path"] = str(task_path)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = {kind: sum(1 for row in rows if row["edit"] == kind) for kind in EDIT_KINDS}
    lines = [
        "# LIBERO-Pro random task preview",
        "",
        f"tasks: {len(rows)}",
        f"goal: {counts['goal']}",
        f"placement: {counts['placement']}",
        f"geometry: {counts['geometry']}",
        "",
        "Placement and geometry tasks still need a newly sampled init file before evaluation.",
        "This run does not start the simulator.",
        "",
    ]
    for kind in EDIT_KINDS:
        lines.append(f"## {kind}")
        lines.append("")
        shown = 0
        for row in rows:
            if row["edit"] != kind:
                continue
            lines.append(f"- `{row['task_id']}`")
            lines.append(f"  - source: {row['source_language']}")
            lines.append(f"  - language: {row['new_language']}")
            lines.append(f"  - change: `{json.dumps(row['detail'], ensure_ascii=False)}`")
            shown += 1
            if shown >= 5:
                break
        lines.append("")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bddl-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-tasks", type=int, default=24)
    parser.add_argument("--suites", nargs="*", default=list(SOURCE_SUITES))
    args = parser.parse_args()
    scenes = collect_scenes(args.bddl_root, tuple(args.suites))
    rows = generate(scenes, random.Random(args.seed), args.max_tasks)
    write_output(rows, args.out_dir)
    print(f"scenes {len(scenes)}")
    print(f"tasks {len(rows)}")
    print(f"out {args.out_dir}")


if __name__ == "__main__":
    main()
