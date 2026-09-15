#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.trigger_scan import (
    ScanConfig,
    load_scan_skills,
    scan_roots,
    write_scan_outputs,
)
from experiments.robot.libero.skill_pipeline.cli_config import (
    diagnostic_provider_roots_for_cli,
    diagnostic_signal_statuses_for_cli,
)
from experiments.robot.libero.skill_pipeline.predicate_registry import load_predicate_registry
from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Offline replay of repair triggers and recovery-hint matches.")
    parser.add_argument("--run-dir", action="append", default=[], help="Raw run dir or archived corpus root.")
    parser.add_argument("--skill-pack", "--skill_pack", dest="skill_pack", default="", help="Optional isolated skill pack name/path.")
    parser.add_argument("--index", default="")
    parser.add_argument("--skill-file", action="append", default=[], help="Additional draft skill to include.")
    parser.add_argument("--mining", action="store_true", help="Load fail_only skills in addition to online skills.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--no-hints", action="store_true", help="Only scan repair triggers.")
    parser.add_argument("--include-empty-query-rows", action="store_true")
    parser.add_argument("--max-queries-per-episode", type=int, default=0)
    parser.add_argument("--predicate-registry", "--predicate_registry", dest="predicate_registry", default="")
    parser.add_argument("--predicate-adapter", "--predicate_adapter", dest="predicate_adapter", default="")
    parser.add_argument(
        "--diagnostic-signal-registry",
        "--diagnostic_signal_registry",
        dest="diagnostic_signal_registry",
        default="",
    )
    parser.add_argument(
        "--diagnostic-signal-statuses",
        "--diagnostic_signal_statuses",
        dest="diagnostic_signal_statuses",
        default="",
    )
    parser.add_argument(
        "--diagnostic-provider-root",
        "--diagnostic_provider_root",
        dest="diagnostic_provider_root",
        action="append",
        default=[],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.run_dir:
        raise SystemExit("at least one --run-dir is required")
    skill_config = resolve_skill_config(
        skill_pack=args.skill_pack or None,
        skill_index=args.index or None,
        predicate_registry=args.predicate_registry or None,
        predicate_adapter=args.predicate_adapter or None,
        diagnostic_signal_registry=args.diagnostic_signal_registry or None,
        repo=REPO_ROOT,
        default_index=REPO_ROOT / "skills" / "_index.yaml",
    )
    predicate_registry = load_predicate_registry(
        skill_config.predicate_registry,
        adapter_path=skill_config.predicate_adapter,
        index_path=skill_config.skill_index,
    )
    skills = load_scan_skills(
        str(skill_config.skill_index),
        extra_skill_files=args.skill_file,
        mining=args.mining,
        predicate_registry=predicate_registry,
    )
    diagnostic_statuses = diagnostic_signal_statuses_for_cli(
        skill_config,
        args.diagnostic_signal_statuses,
        explicit_registry=bool(args.diagnostic_signal_registry),
    )
    report = scan_roots(
        args.run_dir,
        skills,
        ScanConfig(
            include_hints=not args.no_hints,
            include_empty_query_rows=bool(args.include_empty_query_rows),
            max_queries_per_episode=int(args.max_queries_per_episode),
            diagnostic_signal_registry=skill_config.diagnostic_signal_registry,
            diagnostic_signal_statuses=diagnostic_statuses,
            diagnostic_provider_roots=diagnostic_provider_roots_for_cli(
                skill_config,
                args.diagnostic_provider_root,
            ),
        ),
        predicate_registry=predicate_registry,
    )
    outputs = write_scan_outputs(report, args.out_dir)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
