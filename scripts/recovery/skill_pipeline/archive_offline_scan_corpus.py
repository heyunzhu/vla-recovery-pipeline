#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.trace_corpus import archive_run_for_offline_scan, default_corpus_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Archive lightweight rollout traces for offline skill scans.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--repo", default=str(REPO_ROOT))
    parser.add_argument("--corpus-root", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--no-overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = Path(args.repo)
    corpus = Path(args.corpus_root) if args.corpus_root else default_corpus_root(repo)
    manifest = archive_run_for_offline_scan(
        args.run_dir,
        repo_root=repo,
        corpus_root=corpus,
        name=args.name or None,
        overwrite=not args.no_overwrite,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
