#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.grasp_static import (  # noqa: E402
    check_grasp_skill_library,
    render_grasp_static_markdown,
)
from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Run static checks for grasp recovery-hint skills.")
    parser.add_argument("--skill-pack", "--skill_pack", dest="skill_pack", default="", help="Optional isolated skill pack name/path.")
    parser.add_argument("--index", default="")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--md-out", default="")
    parser.add_argument("--skill-file", action="append", default=[], help="Additional draft grasp skill to check.")
    parser.add_argument("--fail-on-warn", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    skill_config = resolve_skill_config(
        skill_pack=args.skill_pack or None,
        skill_index=args.index or None,
        repo=REPO_ROOT,
        default_index=REPO_ROOT / "skills" / "_index.yaml",
    )
    report = check_grasp_skill_library(str(skill_config.skill_index), extra_skill_files=args.skill_file)
    markdown = render_grasp_static_markdown(report)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    if args.md_out:
        Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_out).write_text(markdown, encoding="utf-8")
    if not args.json_out and not args.md_out:
        print(markdown)
    if report.error_count or (args.fail_on_warn and report.warning_count):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
