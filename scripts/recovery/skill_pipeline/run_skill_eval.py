#!/usr/bin/env python3
"""Thin CLI for the skill-pipeline runner. Does not wrap the old eval script."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.runner import main, parse_args

if __name__ == "__main__":
    main(parse_args())
