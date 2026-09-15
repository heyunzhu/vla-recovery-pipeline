#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.grasp_static import (
    check_grasp_skill_library,
    render_grasp_static_markdown,
)
from experiments.robot.libero.skill_pipeline.cli_config import (
    diagnostic_provider_roots_for_cli,
    diagnostic_signal_statuses_for_cli,
)
from experiments.robot.libero.skill_pipeline.generated_benchmark_gate import (
    validate_generated_benchmark,
    validate_generated_smoke_run,
)
from experiments.robot.libero.skill_pipeline.capabilities import load_capability_registry
from experiments.robot.libero.skill_pipeline.predicate_registry import load_predicate_registry
from experiments.robot.libero.skill_pipeline.schema import SkillSchemaError, load_skill
from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config
from experiments.robot.libero.skill_pipeline.trigger_scan import (
    ScanConfig,
    load_scan_skills,
    scan_roots,
    write_scan_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Run static checks and offline scan for a candidate skill.")
    parser.add_argument("--skill-file", required=True)
    parser.add_argument("--scan-root", action="append", default=[], help="Trace corpus or raw run dir.")
    parser.add_argument("--skill-pack", "--skill_pack", dest="skill_pack", default="", help="Optional isolated skill pack name/path.")
    parser.add_argument("--index", default="")
    parser.add_argument(
        "--capability-registry",
        default="",
        help="Optional capability registry. If omitted, use capability_registry from --index when present.",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--mining", action="store_true", help="Load fail_only skills in addition to online skills.")
    parser.add_argument("--no-hints", action="store_true")
    parser.add_argument("--include-empty-query-rows", action="store_true")
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
    parser.add_argument(
        "--generated-benchmark-dir",
        default="",
        help="Frozen generated benchmark directory to validate as part of the gate.",
    )
    parser.add_argument("--generated-split", default="smoke", choices=["smoke", "train", "validation", "all"])
    parser.add_argument(
        "--generated-smoke-run-dir",
        default="",
        help="Existing generated benchmark smoke run dir to validate for episode/trace/video artifacts.",
    )
    parser.add_argument(
        "--require-generated-smoke",
        action="store_true",
        help="Fail if --generated-smoke-run-dir is not provided or does not cover the generated split.",
    )
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
    index_path = str(skill_config.skill_index)
    capability_registry_path = str(skill_config.capability_registry) if skill_config.capability_registry else None
    diagnostic_statuses = diagnostic_signal_statuses_for_cli(
        skill_config,
        args.diagnostic_signal_statuses,
        explicit_registry=bool(args.diagnostic_signal_registry),
    )
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {
        "skill_file": args.skill_file,
        "index": index_path,
        "skill_pack": skill_config.skill_pack.to_summary() if skill_config.skill_pack else {},
        "scan_roots": args.scan_root,
        "static": {},
        "offline_scan": {},
        "generated_benchmark": {},
        "generated_smoke": {},
        "capability_registry": {},
        "capability_audit": {},
        "errors": [],
        "warnings": [],
    }
    errors: list[str] = []
    warnings: list[str] = []
    try:
        predicate_registry = load_predicate_registry(
            skill_config.predicate_registry,
            adapter_path=skill_config.predicate_adapter,
            index_path=skill_config.skill_index,
        )
        result["predicate_registry"] = predicate_registry.summary()
    except Exception as exc:
        predicate_registry = None
        errors.append(f"predicate registry: {exc}")
    try:
        capability_registry = load_capability_registry(capability_registry_path, index_path=index_path)
        result["capability_registry"] = capability_registry.summary()
    except SkillSchemaError as exc:
        capability_registry = None
        errors.append(f"capability registry: {exc}")
    try:
        spec = load_skill(args.skill_file, predicate_registry=predicate_registry)
        result["skill"] = {
            "id": spec.id,
            "kind": spec.kind,
            "scope": spec.scope,
            "track": spec.track,
            "priority": spec.priority,
        }
    except SkillSchemaError as exc:
        errors.append(f"schema: {exc}")
        spec = None

    if spec is not None and capability_registry is not None:
        audit = capability_registry.audit_skill(spec)
        result["capability_audit"] = audit.to_dict()
        errors.extend(f"capability: {item}" for item in audit.errors)
        warnings.extend(f"capability: {item}" for item in audit.warnings)

    if spec is not None and spec.kind == "recovery_hint" and spec.scope == "grasp":
        grasp_report = check_grasp_skill_library(index_path, extra_skill_files=[args.skill_file])
        grasp_md = out / "grasp_static_gate.md"
        grasp_json = out / "grasp_static_gate.json"
        grasp_md.write_text(render_grasp_static_markdown(grasp_report), encoding="utf-8")
        grasp_json.write_text(json.dumps(grasp_report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        result["static"] = {
            "type": "grasp",
            "errors": grasp_report.error_count,
            "warnings": grasp_report.warning_count,
            "markdown": str(grasp_md),
            "json": str(grasp_json),
        }
        if grasp_report.error_count:
            errors.append(f"grasp static gate has {grasp_report.error_count} error(s)")
    elif spec is not None:
        warnings.append(
            "type-specific static gate is not implemented yet; schema validation was applied"
        )
        result["static"] = {"type": spec.scope or spec.kind, "schema_only": True}

    if spec is not None and args.scan_root:
        skills = load_scan_skills(
            index_path,
            extra_skill_files=[args.skill_file],
            mining=args.mining,
            predicate_registry=predicate_registry,
        )
        scan_report = scan_roots(
            args.scan_root,
            skills,
            ScanConfig(
                include_hints=not args.no_hints,
                include_empty_query_rows=args.include_empty_query_rows,
                diagnostic_signal_registry=skill_config.diagnostic_signal_registry,
                diagnostic_signal_statuses=diagnostic_statuses,
                diagnostic_provider_roots=diagnostic_provider_roots_for_cli(
                    skill_config,
                    args.diagnostic_provider_root,
                ),
            ),
            predicate_registry=predicate_registry,
        )
        scan_outputs = write_scan_outputs(scan_report, out / "offline_scan")
        result["offline_scan"] = scan_outputs
    elif spec is not None:
        warnings.append("offline scan skipped because no --scan-root was provided")

    if args.generated_benchmark_dir:
        benchmark_report = validate_generated_benchmark(
            args.generated_benchmark_dir,
            split=args.generated_split,
            require_freeze=True,
        )
        result["generated_benchmark"] = benchmark_report
        if not benchmark_report.get("ok"):
            errors.extend(f"generated benchmark: {item}" for item in benchmark_report.get("errors", []))
        warnings.extend(f"generated benchmark: {item}" for item in benchmark_report.get("warnings", []))

        if args.generated_smoke_run_dir:
            smoke_report = validate_generated_smoke_run(
                args.generated_smoke_run_dir,
                benchmark_dir=args.generated_benchmark_dir,
                split=args.generated_split,
                min_episodes_per_task=max(1, int(args.generated_smoke_min_episodes_per_task)),
                require_video=not args.generated_smoke_no_video,
            )
            result["generated_smoke"] = smoke_report
            if not smoke_report.get("ok"):
                errors.extend(f"generated smoke: {item}" for item in smoke_report.get("errors", []))
            warnings.extend(f"generated smoke: {item}" for item in smoke_report.get("warnings", []))
        elif args.require_generated_smoke:
            errors.append("--require-generated-smoke was set but --generated-smoke-run-dir was not provided")
        else:
            warnings.append("generated smoke validation skipped because no --generated-smoke-run-dir was provided")
    elif args.generated_smoke_run_dir or args.require_generated_smoke:
        errors.append("--generated-benchmark-dir is required for generated smoke validation")

    result["errors"] = errors
    result["warnings"] = warnings
    result["ok"] = not errors
    result_path = out / "skill_quality_gate_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
