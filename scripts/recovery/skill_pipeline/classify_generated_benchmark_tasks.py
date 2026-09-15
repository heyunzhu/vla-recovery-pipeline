#!/usr/bin/env python3
"""Classify generated LIBERO tasks into behavior buckets for skill mining."""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def _norm_name(value: str) -> str:
    text = str(value or "").lower()
    text = re.sub(r"_\d+(_|$)", "_", text)
    return text.strip("_")


def pick_family(name: str) -> str:
    text = _norm_name(name)
    if "black_book" in text or text.endswith("book") or "book_" in text:
        return "book"
    if "white_bowl" in text:
        return "white_bowl"
    if "bowl" in text:
        return "black_bowl"
    if "moka" in text:
        return "moka_pot"
    if "mug" in text or "cup" in text:
        return "mug"
    if any(token in text for token in ("cream_cheese", "butter", "chocolate_pudding")):
        return "flat_box"
    if any(token in text for token in ("alphabet_soup", "tomato_sauce", "ketchup")):
        return "can_or_bottle"
    if any(token in text for token in ("milk", "orange_juice", "salad_dressing")):
        return "carton_bottle"
    return "other"


def target_family(name: str) -> str:
    text = _norm_name(name)
    text = text.replace("_contain_region", "")
    for region in ("front", "back", "left", "right"):
        text = text.replace(f"_{region}", "")
    if "desk_caddy" in text:
        return "desk_caddy"
    if "basket" in text:
        return "basket"
    if "wooden_tray" in text:
        return "wooden_tray"
    if "microwave" in text:
        return "microwave"
    if "plate" in text:
        return "plate"
    if "flat_stove" in text:
        return "flat_stove"
    if "wine_rack" in text:
        return "wine_rack"
    return text or "unknown"


def caddy_region(row: dict[str, Any]) -> str:
    haystack = [str(row.get("language") or "")]
    for atom in row.get("goal_atoms") or []:
        haystack.extend(str(arg) for arg in atom.get("args") or [])
    text = " ".join(haystack).lower()
    for region in ("front", "back", "left", "right"):
        if re.search(rf"\b{region}\b|_{region}_", text):
            return region
    return "generic"


def generated_all_row_ids(rows: list[dict[str, Any]]) -> dict[str, int]:
    sorted_rows = sorted(rows, key=lambda row: str(row.get("task_id") or ""))
    return {str(row.get("task_id")): idx for idx, row in enumerate(sorted_rows, start=1)}


def _object_types_from_bddl(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"\(:objects(?P<body>.*?)\)\s*\(:init", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return {}
    out: dict[str, str] = {}
    for raw in match.group("body").splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or " - " not in line:
            continue
        names_s, type_s = line.split(" - ", 1)
        obj_type = type_s.strip().split()[0]
        for name in names_s.split():
            out[name.strip()] = obj_type
    return out


def _pick_clause(language: str) -> str:
    text = str(language or "").lower()
    for marker in (" and place", " then place", " and put", " then put"):
        if marker in text:
            return text.split(marker, 1)[0]
    return text


def _pick_clause_has_disambiguator(language: str) -> bool:
    text = _pick_clause(language)
    return bool(re.search(r"\b(front|back|left|right|middle|rear|nearest|farthest|closest)\b", text))


def _ambiguous_pick_reason(row: dict[str, Any], pick: str, object_types: dict[str, str]) -> tuple[str, int, str]:
    pick_type = object_types.get(pick, "")
    if not pick_type:
        return "", 0, ""
    same_type_count = sum(1 for obj_type in object_types.values() if obj_type == pick_type)
    if same_type_count <= 1:
        return "", same_type_count, pick_type
    if _pick_clause_has_disambiguator(str(row.get("language") or "")):
        return "", same_type_count, pick_type
    return (
        f"ambiguous pick object: {same_type_count} instances of `{pick_type}` but the pick clause does not disambiguate which one",
        same_type_count,
        pick_type,
    )


def classify_row(row: dict[str, Any], all_row_by_id: dict[str, int], benchmark_dir: Path) -> dict[str, Any]:
    out = dict(row)
    obj_interest = list(row.get("obj_of_interest") or [])
    pick = str(obj_interest[0] if obj_interest else "")
    target = str(obj_interest[1] if len(obj_interest) > 1 else "")
    object_types = _object_types_from_bddl(benchmark_dir / str(row.get("bddl_path") or ""))
    ambiguous_reason, pick_type_count, pick_type = _ambiguous_pick_reason(row, pick, object_types)
    template = str(row.get("template") or "unknown")
    p_family = pick_family(pick)
    t_family = target_family(target)
    region = caddy_region(row) if t_family == "desk_caddy" else "none"
    if template == "caddy_compartment":
        behavior = f"caddy_compartment/{p_family}"
        fine = f"{behavior}/{region}"
    elif template == "put_inside_container":
        behavior = f"inside/{t_family}/{p_family}"
        fine = f"{behavior}/{region}" if t_family == "desk_caddy" else behavior
    elif template == "pick_place_on_surface":
        behavior = f"surface/{t_family}/{p_family}"
        fine = behavior
    else:
        behavior = f"{template}/{t_family}/{p_family}"
        fine = behavior
    task_id = str(row.get("task_id") or "")
    out.update(
        {
            "all_row_id_1based": all_row_by_id.get(task_id, 0),
            "runner_generated_split": "all",
            "runner_selector": str(all_row_by_id.get(task_id, 0)),
            "behavior_category": behavior,
            "fine_category": fine,
            "pick_object": pick,
            "pick_type": pick_type,
            "pick_type_instance_count": pick_type_count,
            "pick_family": p_family,
            "target_object": target,
            "target_family": t_family,
            "target_region": region,
            "first_pass_exclude_reason": first_pass_exclude_reason(row, t_family, ambiguous_reason),
        }
    )
    return out


def first_pass_exclude_reason(row: dict[str, Any], t_family: str, ambiguous_reason: str = "") -> str:
    reasons: list[str] = []
    if ambiguous_reason:
        reasons.append(ambiguous_reason)
    language = str(row.get("language") or "").lower()
    if t_family == "microwave" and " in the microwave" in language:
        reasons.append("microwave-inside generated tasks are known to be brittle for first-pass harness canaries")
    return "; ".join(reasons)


def _rank_key(seed: int, row: dict[str, Any]) -> str:
    task_id = str(row.get("task_id") or "")
    return hashlib.sha1(f"{seed}:{task_id}".encode("utf-8")).hexdigest()


def split_rows(rows: list[dict[str, Any]], *, seed: int, test_fraction: float, min_test: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    by_category: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        if row.get("first_pass_exclude_reason"):
            continue
        by_category[str(row["behavior_category"])].append(row)
    for category, items in sorted(by_category.items()):
        ranked = sorted(items, key=lambda row: _rank_key(seed, row))
        if len(ranked) <= 1:
            train.extend(ranked)
            continue
        count = max(min_test, round(len(ranked) * test_fraction))
        count = min(count, len(ranked) - 1)
        test.extend(ranked[:count])
        train.extend(ranked[count:])
    return sorted(train, key=lambda row: int(row["all_row_id_1based"])), sorted(test, key=lambda row: int(row["all_row_id_1based"]))


def sample_phase(rows: list[dict[str, Any]], *, seed: int, limit_per_category: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_category: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        by_category[str(row["behavior_category"])].append(row)
    for _, items in sorted(by_category.items()):
        out.extend(sorted(items, key=lambda row: _rank_key(seed + 17, row))[:limit_per_category])
    return sorted(out, key=lambda row: int(row["all_row_id_1based"]))


def summarize(rows: list[dict[str, Any]], train: list[dict[str, Any]], test: list[dict[str, Any]], phase_train: list[dict[str, Any]], phase_test: list[dict[str, Any]]) -> dict[str, Any]:
    def counts(items: list[dict[str, Any]], key: str) -> dict[str, int]:
        return dict(sorted(collections.Counter(str(row.get(key) or "") for row in items).items()))

    category_rows = []
    categories = sorted({str(row["behavior_category"]) for row in rows})
    for category in categories:
        items = [row for row in rows if row["behavior_category"] == category]
        category_rows.append(
            {
                "category": category,
                "total": len(items),
                "original_splits": counts(items, "split"),
                "pick_families": counts(items, "pick_family"),
                "target_families": counts(items, "target_family"),
                "target_regions": counts(items, "target_region"),
                "train": sum(1 for row in train if row["behavior_category"] == category),
                "test": sum(1 for row in test if row["behavior_category"] == category),
                "phase_train": sum(1 for row in phase_train if row["behavior_category"] == category),
                "phase_test": sum(1 for row in phase_test if row["behavior_category"] == category),
                "excluded_first_pass": sum(1 for row in items if row.get("first_pass_exclude_reason")),
                "example": items[0].get("language") if items else "",
            }
        )
    return {
        "schema_version": 1,
        "total_tasks": len(rows),
        "original_splits": counts(rows, "split"),
        "templates": counts(rows, "template"),
        "behavior_categories": category_rows,
        "derived_split_counts": {
            "train": len(train),
            "test": len(test),
            "phase_train": len(phase_train),
            "phase_test": len(phase_test),
        },
        "first_pass_excluded": counts([row for row in rows if row.get("first_pass_exclude_reason")], "first_pass_exclude_reason"),
    }


def write_category_dirs(out_dir: Path, rows: list[dict[str, Any]]) -> None:
    category_root = out_dir / "categories"
    if category_root.exists():
        shutil.rmtree(category_root)
    by_category: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        by_category[str(row["behavior_category"])].append(row)
    for category, items in sorted(by_category.items()):
        folder = category_root / _safe_name(category)
        folder.mkdir(parents=True, exist_ok=True)
        sorted_items = sorted(items, key=lambda row: int(row["all_row_id_1based"]))
        _write_jsonl(folder / "tasks.jsonl", sorted_items)
        selectors = ",".join(str(row["all_row_id_1based"]) for row in sorted_items)
        (folder / "selectors_all_split.txt").write_text(selectors + "\n", encoding="utf-8")


def render_markdown(summary: dict[str, Any], rows: list[dict[str, Any]], phase_train: list[dict[str, Any]], phase_test: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "# Generated Benchmark Task Categories",
        "",
        "This file classifies the frozen generated LIBERO benchmark into behavior",
        "buckets for scratch skill mining. It does not modify the benchmark BDDL",
        "or the original frozen manifests.",
        "",
        "## Overall",
        "",
        f"- Tasks: `{summary['total_tasks']}`",
        f"- Original splits: `{summary['original_splits']}`",
        f"- Templates: `{summary['templates']}`",
        f"- Derived split counts: `{summary['derived_split_counts']}`",
        "",
        "Runner usage: set `--generated_split all` and pass the comma-separated",
        "`all_row_id_1based` selectors from the desired category file.",
        "",
        "## Categories",
        "",
        "| category | total | train | test | phase train | phase test | excluded | example |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summary["behavior_categories"]:
        example = str(item.get("example") or "").replace("|", "\\|")
        lines.append(
            f"| `{item['category']}` | {item['total']} | {item['train']} | {item['test']} | "
            f"{item['phase_train']} | {item['phase_test']} | {item['excluded_first_pass']} | {example} |"
        )
    lines.extend(
        [
            "",
            "## Phase-1 Train Sample",
            "",
            "| selector | task id | category | language |",
            "| ---: | --- | --- | --- |",
        ]
    )
    for row in phase_train:
        language = str(row.get("language") or "").replace("|", "\\|")
        lines.append(
            f"| {row['all_row_id_1based']} | `{row['task_id']}` | `{row['behavior_category']}` | "
            f"{language} |"
        )
    lines.extend(
        [
            "",
            "## Phase-1 Test Sample",
            "",
            "| selector | task id | category | language |",
            "| ---: | --- | --- | --- |",
        ]
    )
    for row in phase_test:
        language = str(row.get("language") or "").replace("|", "\\|")
        lines.append(
            f"| {row['all_row_id_1based']} | `{row['task_id']}` | `{row['behavior_category']}` | "
            f"{language} |"
        )
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "all_row_id_1based",
        "task_id",
        "split",
        "template",
        "behavior_category",
        "fine_category",
        "pick_object",
        "pick_type",
        "pick_type_instance_count",
        "pick_family",
        "target_object",
        "target_family",
        "target_region",
        "language",
        "source_task_id_1based",
        "first_pass_exclude_reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark-dir",
        default=str(_repo_root() / "benchmarks" / "libero90_generated_v1_envfiltered_304"),
    )
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--seed", type=int, default=73)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--min-test-per-category", type=int, default=1)
    parser.add_argument("--phase-train-per-category", type=int, default=4)
    parser.add_argument("--phase-test-per-category", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark = Path(args.benchmark_dir)
    out_dir = Path(args.out_dir) if args.out_dir else benchmark / "category_splits" / "by_behavior_v1"
    raw_rows = _read_jsonl(benchmark / "manifests" / "all_tasks.jsonl")
    all_row_by_id = generated_all_row_ids(raw_rows)
    rows = sorted(
        [classify_row(row, all_row_by_id, benchmark) for row in raw_rows],
        key=lambda row: int(row["all_row_id_1based"]),
    )
    train, test = split_rows(
        rows,
        seed=int(args.seed),
        test_fraction=float(args.test_fraction),
        min_test=int(args.min_test_per_category),
    )
    phase_train = sample_phase(train, seed=int(args.seed), limit_per_category=int(args.phase_train_per_category))
    phase_test = sample_phase(test, seed=int(args.seed), limit_per_category=int(args.phase_test_per_category))
    summary = summarize(rows, train, test, phase_train, phase_test)

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "categorized_tasks.jsonl", rows)
    _write_jsonl(out_dir / "train_tasks.jsonl", train)
    _write_jsonl(out_dir / "test_tasks.jsonl", test)
    _write_jsonl(out_dir / "phase1_train_tasks.jsonl", phase_train)
    _write_jsonl(out_dir / "phase1_test_tasks.jsonl", phase_test)
    write_csv(out_dir / "categorized_tasks.csv", rows)
    (out_dir / "train_selectors_all_split.txt").write_text(
        ",".join(str(row["all_row_id_1based"]) for row in train) + "\n",
        encoding="utf-8",
    )
    (out_dir / "test_selectors_all_split.txt").write_text(
        ",".join(str(row["all_row_id_1based"]) for row in test) + "\n",
        encoding="utf-8",
    )
    (out_dir / "phase1_train_selectors_all_split.txt").write_text(
        ",".join(str(row["all_row_id_1based"]) for row in phase_train) + "\n",
        encoding="utf-8",
    )
    (out_dir / "phase1_test_selectors_all_split.txt").write_text(
        ",".join(str(row["all_row_id_1based"]) for row in phase_test) + "\n",
        encoding="utf-8",
    )
    (out_dir / "category_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "category_summary.md").write_text(
        render_markdown(summary, rows, phase_train, phase_test),
        encoding="utf-8",
    )
    write_category_dirs(out_dir, rows)
    print(json.dumps({"out_dir": str(out_dir), **summary["derived_split_counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
