#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.code_admission import (
    CodeAdmissionConfig,
    run_code_admission,
)
from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Run the code admission gate for skill-owned code changes.")
    parser.add_argument("--manifest", default="", help="code_patch_manifest.yaml produced with the draft.")
    parser.add_argument("--skill-file", action="append", default=[], help="Candidate skill markdown to audit.")
    parser.add_argument("--skill-pack", "--skill_pack", dest="skill_pack", default="", help="Optional isolated skill pack name/path.")
    parser.add_argument("--index", default="")
    parser.add_argument("--capability-registry", default="")
    parser.add_argument("--predicate-registry", "--predicate_registry", dest="predicate_registry", default="")
    parser.add_argument("--predicate-adapter", "--predicate_adapter", dest="predicate_adapter", default="")
    parser.add_argument("--base-ref", default="HEAD")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--fail-on-empty-diff", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (str(args.skill_pack).strip() or str(args.index).strip()):
        raise SystemExit("provide --skill-pack or --index; implicit root skill libraries are not supported")
    skill_config = resolve_skill_config(
        skill_pack=args.skill_pack or None,
        skill_index=args.index or None,
        capability_registry=args.capability_registry or None,
        predicate_registry=args.predicate_registry or None,
        predicate_adapter=args.predicate_adapter or None,
        repo=REPO_ROOT,
    )
    result = run_code_admission(
        CodeAdmissionConfig(
            repo_root=args.repo_root,
            out_dir=args.out_dir,
            manifest_path=args.manifest or None,
            skill_files=args.skill_file,
            index_path=str(skill_config.skill_index),
            capability_registry=str(skill_config.capability_registry) if skill_config.capability_registry else None,
            predicate_registry=str(skill_config.predicate_registry) if skill_config.predicate_registry else None,
            predicate_adapter=str(skill_config.predicate_adapter) if skill_config.predicate_adapter else None,
            pack_root=str(skill_config.skill_pack.root) if skill_config.skill_pack else None,
            base_ref=args.base_ref,
            allow_empty_diff=not bool(args.fail_on_empty_diff),
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
