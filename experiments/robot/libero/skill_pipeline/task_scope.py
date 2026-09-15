"""Decide which benchmark tasks the pick-place recovery stack can address.

The screen reads a task's BDDL and looks at the **goal atoms** only, because that
is what decides whether the cuTAMP recovery path has anything to do:

* ``On(A, B)`` / ``In(A, B)`` (chained ``On`` for stacks) -> the goal is a
  placement, so a pick-and-place recovery can express it.
* ``Open`` / ``Close`` -> an articulated object has to be moved.
* ``TurnOn`` -> the atom is dropped by the goal parser, so it is detected by
  scanning the raw goal section instead.

The screen is offline and cheap: it never loads a scene, and it only needs the
BDDL files that the LIBERO config already points at (``bddl_files`` in
``<run_root>/libero_config/config.yaml``).
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from experiments.robot.libero.tiptop_repro.bddl_goals import parse_bddl_task_goals

PICK_PLACE_PREDICATES = frozenset({"on", "inside"})
ARTICULATED_PREDICATES = frozenset({"open", "close", "closed", "turnon", "turn_on"})
PUSH_PREDICATES = frozenset({"push", "slide"})
# Push-style tasks can parse as a placement goal (e.g. ``On(plate, stove)``), so
# they are recognised from the task language and kept out of scope by default.
PUSH_VERBS = ("push", "slide", "nudge")

SCOPE_PICK_PLACE = "pick_place"
SCOPE_ARTICULATED = "articulated"
SCOPE_PUSH = "push"
SCOPE_MIXED = "mixed"
SCOPE_UNKNOWN = "unknown"
OUT_OF_SCOPE = (SCOPE_ARTICULATED, SCOPE_PUSH, SCOPE_MIXED, SCOPE_UNKNOWN)

_ATOM_RE = re.compile(r"\(\s*([A-Za-z_][A-Za-z0-9_]*)")


def _goal_section(text: str) -> str:
    """Return the raw ``(:goal ...)`` body, or "" when there is none."""
    start = text.find("(:goal")
    if start < 0:
        return ""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:]


def raw_goal_predicates(text: str) -> list[str]:
    """Every ``(predicate ...)`` token inside the goal section, lowercased."""
    out: list[str] = []
    for match in _ATOM_RE.finditer(_goal_section(text)):
        name = match.group(1).lower()
        if name not in {"and", "or", "not"} and name not in out:
            out.append(name)
    return out


def classify_goal_atoms(
    atoms: Sequence[Mapping[str, Any]],
    *,
    raw_predicates: Iterable[str] = (),
    language: str = "",
) -> tuple[str, str, list[str]]:
    """Return ``(scope, reason, notes)`` for parsed goal atoms."""
    parsed = {str(atom.get("predicate") or "").lower() for atom in atoms}
    raw = {str(item).lower() for item in raw_predicates}
    placement = sorted(parsed & PICK_PLACE_PREDICATES)
    articulated = sorted((parsed | raw) & ARTICULATED_PREDICATES)
    push_atoms = sorted((parsed | raw) & PUSH_PREDICATES)
    unsupported = sorted(raw - parsed - ARTICULATED_PREDICATES - PUSH_PREDICATES - {"and"})
    notes: list[str] = []
    if len([atom for atom in atoms if str(atom.get("predicate") or "") == "on"]) >= 2:
        notes.append("stack")
    if any("region" in str(arg) for atom in atoms for arg in atom.get("args") or []):
        notes.append("region_goal")
    push_verbs = [verb for verb in PUSH_VERBS if re.search(rf"\b{verb}", language.lower())]
    if push_verbs:
        notes.append("push_language")

    if articulated and placement:
        return SCOPE_MIXED, f"placement {placement} plus articulated {articulated}", notes
    if articulated:
        return SCOPE_ARTICULATED, f"articulated goal predicate: {articulated}", notes
    if (push_atoms or push_verbs) and placement:
        return (
            SCOPE_PUSH,
            f"push-style goal ({push_atoms or push_verbs}) over a placement goal {placement}",
            notes,
        )
    if placement:
        return SCOPE_PICK_PLACE, f"placement goal: {placement}", notes
    if push_atoms or push_verbs:
        return SCOPE_PUSH, f"push-style goal without a placement atom: {push_atoms or push_verbs}", notes
    return (
        SCOPE_UNKNOWN,
        f"no supported goal atom (unsupported predicates: {unsupported or 'none'})",
        notes,
    )


@dataclass
class TaskScope:
    path: str
    task_name: str
    language: str = ""
    obj_of_interest: list[str] = field(default_factory=list)
    goal_atoms: list[dict[str, Any]] = field(default_factory=list)
    raw_goal_predicates: list[str] = field(default_factory=list)
    scope: str = SCOPE_UNKNOWN
    reason: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def in_scope(self) -> bool:
        return self.scope == SCOPE_PICK_PLACE

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "task_name": self.task_name,
            "language": self.language,
            "obj_of_interest": list(self.obj_of_interest),
            "goal_atoms": [dict(atom) for atom in self.goal_atoms],
            "raw_goal_predicates": list(self.raw_goal_predicates),
            "scope": self.scope,
            "in_scope": self.in_scope,
            "reason": self.reason,
            "notes": list(self.notes),
        }


def classify_bddl_text(text: str, *, path: str = "", task_name: str = "") -> TaskScope:
    parsed = parse_bddl_task_goals(text)
    atoms = list(parsed.get("goal_atoms") or [])
    raw = raw_goal_predicates(text)
    language = str(parsed.get("language") or "")
    scope, reason, notes = classify_goal_atoms(atoms, raw_predicates=raw, language=language)
    return TaskScope(
        path=path,
        task_name=task_name or (Path(path).stem if path else ""),
        language=language,
        obj_of_interest=[str(item) for item in parsed.get("obj_of_interest") or []],
        goal_atoms=[dict(atom) for atom in atoms],
        raw_goal_predicates=raw,
        scope=scope,
        reason=reason,
        notes=notes,
    )


def classify_bddl_file(path: str | Path) -> TaskScope:
    file_path = Path(path)
    return classify_bddl_text(
        file_path.read_text(encoding="utf-8"),
        path=str(file_path),
        task_name=file_path.stem,
    )


def screen_bddl_dir(bddl_dir: str | Path, *, suite: str = "", pattern: str = "*.bddl") -> dict[str, Any]:
    """Classify every BDDL in one suite directory, in filename order."""
    root = Path(bddl_dir)
    files = sorted(root.glob(pattern)) if root.is_dir() else []
    rows = [classify_bddl_file(path) for path in files]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.scope] = counts.get(row.scope, 0) + 1
    return {
        "schema_version": 1,
        "suite": suite or root.name,
        "bddl_dir": str(root),
        "task_count": len(rows),
        "in_scope_count": sum(1 for row in rows if row.in_scope),
        "counts": counts,
        "tasks": [row.to_dict() for row in rows],
    }


def bddl_root_from_libero_config(config_path: str | Path) -> Path | None:
    """Read ``bddl_files`` from a LIBERO config.yaml written by the launcher."""
    path = Path(config_path)
    if not path.exists():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    raw = str((data or {}).get("bddl_files") or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else path.parent / candidate


def screen_suite(
    *,
    bddl_root: str | Path | None = None,
    suite: str = "",
    libero_config: str | Path | None = None,
    bddl_file: str | Path | None = None,
) -> dict[str, Any]:
    """Screen one suite directory, one explicit BDDL file, or both."""
    if bddl_file is not None:
        row = classify_bddl_file(bddl_file)
        return {
            "schema_version": 1,
            "suite": suite or Path(bddl_file).stem,
            "bddl_dir": str(Path(bddl_file).parent),
            "task_count": 1,
            "in_scope_count": 1 if row.in_scope else 0,
            "counts": {row.scope: 1},
            "tasks": [row.to_dict()],
        }
    root = Path(bddl_root) if bddl_root else None
    if root is None and libero_config:
        root = bddl_root_from_libero_config(libero_config)
    if root is None:
        raise SystemExit("provide --bddl-root, --libero-config, or --bddl-file")
    return screen_bddl_dir(root / suite if suite else root, suite=suite)


def render_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        f"# Task scope screen: {result.get('suite', '')}",
        "",
        f"- BDDL dir: `{result.get('bddl_dir', '')}`",
        f"- tasks: {result.get('task_count', 0)}  in scope: {result.get('in_scope_count', 0)}",
        f"- classes: {result.get('counts') or {}}",
        "",
        "| # | task | scope | goal atoms | reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(result.get("tasks") or [], start=1):
        atoms = ", ".join(
            f"{atom.get('predicate')}({', '.join(str(a) for a in atom.get('args') or [])})"
            for atom in row.get("goal_atoms") or []
        )
        lines.append(
            f"| {index} | {row.get('task_name', '')} | {row.get('scope', '')} | {atoms or '-'} | {row.get('reason', '')} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser("Screen benchmark tasks for pick-place scope from their BDDL goals.")
    parser.add_argument("--bddl-root", default="", help="e.g. <LIBERO>/libero/libero/bddl_files")
    parser.add_argument("--suite", default="", help="e.g. libero_goal_swap")
    parser.add_argument("--bddl-file", default="", help="Classify a single BDDL file.")
    parser.add_argument("--libero-config", default="", help="Read bddl_files from a LIBERO config.yaml.")
    parser.add_argument("--out", default="", help="Write the JSON result here.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a markdown table.")
    args = parser.parse_args(argv)

    result = screen_suite(
        bddl_root=args.bddl_root or None,
        suite=args.suite,
        libero_config=args.libero_config or None,
        bddl_file=args.bddl_file or None,
    )
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render_markdown(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
