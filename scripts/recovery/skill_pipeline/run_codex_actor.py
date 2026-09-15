#!/usr/bin/env python3
"""Offline Codex actor wrapper. Never imported by the online runner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


sys.path.insert(0, str(_repo_root()))

from experiments.robot.libero.skill_pipeline.coordinator import check_draft
from experiments.robot.libero.skill_pipeline.schema import load_index, parse_skill_markdown
from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config
sys.path.insert(0, str(Path(__file__).resolve().parent))
from actor_context import GUIDELINE_FILES, guideline_index


PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "actor.md"
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Pack a prompt for the offline skill actor.")
    parser.add_argument("--evidence_json", default="", help="pair.json or fail_set.json rollout evidence.")
    parser.add_argument("--pack_json", default="", help="Deprecated alias of --evidence_json.")
    parser.add_argument("--pair_json", default="", help="Deprecated alias of --evidence_json.")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument(
        "--skill_pack",
        "--skill-pack",
        dest="skill_pack",
        default="",
        help="Optional isolated skill pack name/path. Explicit --skills_dir overrides pack defaults.",
    )
    parser.add_argument("--skills_dir", default="")
    parser.add_argument("--draft_md", default="", help="If set, validate this draft instead of writing a prompt.")
    parser.add_argument(
        "--track",
        default="",
        help="Optional override for draft checks: pair or fail_only.",
    )
    return parser.parse_args()


def _library_excerpt(skills_dir: Path) -> str:
    if not skills_dir.exists():
        return "(no skills/ directory)"
    chunks = []
    index = skills_dir / "_index.yaml"
    if index.exists():
        chunks.append(f"# _index.yaml\n{index.read_text(encoding='utf-8')}")
    for path in sorted(skills_dir.rglob("*.md")):
        rel = path.relative_to(skills_dir)
        chunks.append(f"# {rel.as_posix()}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(chunks) if chunks else "(empty skill library)"


def _read_limited(path: Path, *, max_chars: int = 24000) -> str:
    text = path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[truncated for actor prompt]\n"


def _guideline_excerpt(repo: Path) -> str:
    return guideline_index(repo)


def _capability_excerpt(skills_dir: Path) -> str:
    index = skills_dir / "_index.yaml"
    if not index.exists():
        return "(no _index.yaml; no capability registry declared)"
    try:
        data = load_index(index)
    except Exception as exc:
        return f"(could not parse _index.yaml: {type(exc).__name__}: {exc})"
    rel = str(data.get("capability_registry") or "").strip()
    if not rel:
        return "(no capability_registry declared; implicit legacy allow-all)"
    path = Path(rel)
    if not path.is_absolute():
        path = index.parent / path
    if not path.exists():
        return f"(capability registry declared but missing: {path})"
    return f"# {path}\n{_read_limited(path, max_chars=12000)}"


def render_actor_prompt(evidence_text: str, skills_dir: Path, *, extra: str = "") -> str:
    repo = Path(__file__).resolve().parents[3]
    chunks = [
        PROMPT_PATH.read_text(encoding="utf-8"),
        "## Capability registry for this skill library\n",
        _capability_excerpt(skills_dir),
        "## Skill-type authoring guidelines\n",
        _guideline_excerpt(repo),
        "## Current skill library (read pair/ and fail_only/; do not mix tracks)\n",
        _library_excerpt(skills_dir),
        extra,
        "## Rollout evidence JSON\n",
        evidence_text,
    ]
    return "\n\n".join(item for item in chunks if item)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.draft_md:
        spec = parse_skill_markdown(Path(args.draft_md).read_text(encoding="utf-8"), path=args.draft_md)
        if args.track:
            spec.track = args.track
        report = check_draft(spec)
        (out_dir / "coordinator_report.json").write_text(
            json.dumps(
                {
                    "ok": report.ok,
                    "online_ready": report.online_ready,
                    "track": report.track,
                    "library": report.library,
                    "errors": report.errors,
                    "warnings": report.warnings,
                    "skill_id": spec.id,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if not report.ok:
            raise SystemExit("draft failed schema/coordinator checks: " + "; ".join(report.errors))
        print(f"draft ok id={spec.id} track={report.track} online_ready={report.online_ready}")
        return

    evidence_path = args.evidence_json or args.pack_json or args.pair_json
    if not evidence_path:
        raise SystemExit("provide --evidence_json (or legacy --pack_json/--pair_json) unless --draft_md is set")
    evidence = Path(evidence_path).read_text(encoding="utf-8")
    skill_config = resolve_skill_config(
        skill_pack=args.skill_pack or None,
        skills_dir=args.skills_dir or None,
        repo=Path(__file__).resolve().parents[3],
    )
    skills_dir = skill_config.skills_dir
    prompt = render_actor_prompt(evidence, skills_dir)
    (out_dir / "actor_prompt.md").write_text(prompt, encoding="utf-8")
    print(str(out_dir / "actor_prompt.md"))


if __name__ == "__main__":
    main()
