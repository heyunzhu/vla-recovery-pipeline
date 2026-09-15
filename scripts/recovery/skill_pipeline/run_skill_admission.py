#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.admission import (
    DEFAULT_MIN_FIRST_REPAIR_QUERY_IDX,
    SkillAdmissionConfig,
    resolve_admission_scan_roots,
    run_skill_admission,
)
from experiments.robot.libero.skill_pipeline.cli_config import (
    diagnostic_provider_roots_for_cli,
    diagnostic_signal_statuses_for_cli,
)
from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config
from experiments.robot.libero.skill_pipeline.validate import SUCCESS_EPISODE_FIRE_MAX


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Run the admission gate for a candidate skill.")
    parser.add_argument("--skill-file", required=True)
    parser.add_argument("--skill-pack", "--skill_pack", dest="skill_pack", default="", help="Optional isolated skill pack name/path.")
    parser.add_argument("--index", default="")
    parser.add_argument(
        "--capability-registry",
        default="",
        help="Optional capability registry. If omitted, use capability_registry from --index when present.",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--scan-root",
        action="append",
        default=[],
        help="Additional offline trigger corpus/canary root. Repeat for multiple corpora.",
    )
    parser.add_argument(
        "--corpus-root",
        default="analysis_outputs/offline_trigger_corpus",
        help="Rolling corpus root used when --scan-root is omitted.",
    )
    parser.add_argument("--max-corpus-runs", type=int, default=8)
    parser.add_argument(
        "--fallback-scan-root",
        default="",
        help="Current task/run trace root. Included in the global scan alongside corpus roots.",
    )
    parser.add_argument(
        "--current-task-id",
        action="append",
        type=int,
        default=[],
        help="Task id(s) treated as the current mining target within --fallback-scan-root.",
    )
    parser.add_argument(
        "--current-task-name",
        action="append",
        default=[],
        help="Task directory name(s) treated as the current mining target within --fallback-scan-root.",
    )
    parser.add_argument("--mining", action="store_true", help="Load fail_only skills in addition to online skills.")
    parser.add_argument(
        "--allow-missing-scan",
        action="store_true",
        help="Do not fail when no --scan-root is provided.",
    )
    parser.add_argument(
        "--allow-current-only-scan",
        action="store_true",
        help="Debug only: allow admission when the scan contains no non-current episodes.",
    )
    parser.add_argument("--no-hints", action="store_true")
    parser.add_argument("--include-empty-query-rows", action="store_true")
    parser.add_argument("--max-queries-per-episode", type=int, default=0)
    parser.add_argument("--max-success-episode-match-rate", type=float, default=SUCCESS_EPISODE_FIRE_MAX)
    parser.add_argument("--max-success-winner-episode-matches", type=int, default=0)
    parser.add_argument("--min-first-repair-query-idx", type=int, default=DEFAULT_MIN_FIRST_REPAIR_QUERY_IDX)
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
    parser.add_argument("--generated-benchmark-dir", default="")
    parser.add_argument("--generated-split", default="smoke", choices=["smoke", "train", "validation", "all"])
    parser.add_argument("--generated-smoke-run-dir", default="")
    parser.add_argument("--require-generated-smoke", action="store_true")
    parser.add_argument("--generated-smoke-min-episodes-per-task", type=int, default=1)
    parser.add_argument("--generated-smoke-no-video", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    skill_config = resolve_skill_config(
        skill_pack=args.skill_pack or None,
        skill_index=args.index or None,
        capability_registry=args.capability_registry or None,
        predicate_registry=args.predicate_registry or None,
        predicate_adapter=args.predicate_adapter or None,
        diagnostic_signal_registry=args.diagnostic_signal_registry or None,
        repo=REPO_ROOT,
        default_index=REPO_ROOT / "skills" / "_index.yaml",
    )
    diagnostic_statuses = diagnostic_signal_statuses_for_cli(
        skill_config,
        args.diagnostic_signal_statuses,
        explicit_registry=bool(args.diagnostic_signal_registry),
    )
    scan_roots = resolve_admission_scan_roots(
        args.scan_root,
        repo_root=REPO_ROOT,
        corpus_root=args.corpus_root,
        max_corpus_runs=int(args.max_corpus_runs),
        fallback_scan_root=args.fallback_scan_root or None,
    )
    result = run_skill_admission(
        args.skill_file,
        config=SkillAdmissionConfig(
            index_path=str(skill_config.skill_index),
            out_dir=args.out_dir,
            scan_roots=tuple(scan_roots),
            current_scan_roots=tuple([args.fallback_scan_root] if args.fallback_scan_root else []),
            current_task_ids=tuple(args.current_task_id),
            current_task_names=tuple(args.current_task_name),
            mining=bool(args.mining),
            require_offline_scan=not bool(args.allow_missing_scan),
            allow_current_only_scan=bool(args.allow_current_only_scan),
            include_hints=not bool(args.no_hints),
            include_empty_query_rows=bool(args.include_empty_query_rows),
            max_queries_per_episode=int(args.max_queries_per_episode),
            max_success_episode_match_rate=float(args.max_success_episode_match_rate),
            max_success_winner_episode_matches=int(args.max_success_winner_episode_matches),
            min_first_repair_query_idx=int(args.min_first_repair_query_idx),
            generated_benchmark_dir=args.generated_benchmark_dir or None,
            generated_split=args.generated_split,
            generated_smoke_run_dir=args.generated_smoke_run_dir or None,
            require_generated_smoke=bool(args.require_generated_smoke),
            generated_smoke_min_episodes_per_task=int(args.generated_smoke_min_episodes_per_task),
            generated_smoke_require_video=not bool(args.generated_smoke_no_video),
            capability_registry=str(skill_config.capability_registry) if skill_config.capability_registry else None,
            predicate_registry=str(skill_config.predicate_registry) if skill_config.predicate_registry else None,
            predicate_adapter=str(skill_config.predicate_adapter) if skill_config.predicate_adapter else None,
            diagnostic_signal_registry=str(skill_config.diagnostic_signal_registry)
            if skill_config.diagnostic_signal_registry
            else None,
            diagnostic_signal_statuses=diagnostic_statuses,
            diagnostic_provider_roots=diagnostic_provider_roots_for_cli(
                skill_config,
                args.diagnostic_provider_root,
            ),
        ),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
