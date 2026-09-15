#!/usr/bin/env python3
"""Offline mining loop: write, same-init validate at 3/5, at most 3 Codex writes.

Never imported by the online runner. Codex is not invoked here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Task-loop skill mining (offline).")
    parser.add_argument("command", choices=["step", "ingest", "score", "status"])
    parser.add_argument("--run_dir", required=True, help="Skills-off baseline containing taskXX/epYY/")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument(
        "--skill_pack",
        "--skill-pack",
        dest="skill_pack",
        default="",
        help="Optional isolated skill pack name/path. Explicit --skills_dir/--capability_registry override pack defaults.",
    )
    parser.add_argument("--skills_dir", default="")
    parser.add_argument(
        "--capability_registry",
        default="",
        help="Optional capability registry. If omitted, use capability_registry from --skills_dir/_index.yaml.",
    )
    parser.add_argument("--task_ids", default="", help="e.g. 1-20 or 1,2,3. Default: discover run_dir.")
    parser.add_argument("--draft_md", default="", help="For ingest: Codex draft.md")
    parser.add_argument("--bundle_yaml", default="", help="For ingest: Codex skill bundle manifest.")
    parser.add_argument("--draft_dir", default="", help="For ingest: directory containing bundle.yaml or markdown drafts.")
    parser.add_argument(
        "--enable_code_admission_gate",
        action="store_true",
        help="Run code admission before ingesting a draft that changed Python capabilities.",
    )
    parser.add_argument(
        "--code_manifest",
        default="",
        help="code_patch_manifest.yaml produced with the draft. Also enables code admission.",
    )
    parser.add_argument("--code_base_ref", default="HEAD")
    parser.add_argument("--code_base_snapshot", default="", help="Daemon-owned pre-patch file texts for transactional pack admission")
    parser.add_argument("--code_admission_out_dir", default="", help="Default: <out_dir>/taskXX/code_admission_wN")
    parser.add_argument("--task_id", type=int, default=0, help="Default is awaiting_task.")
    parser.add_argument("--on_dir", default="", help="For score: same-init run with --enable_mining_skills")
    parser.add_argument("--enable_admission_gate", action="store_true", help="Run admission before ingesting a draft.")
    parser.add_argument(
        "--admission_scan_root",
        action="append",
        default=[],
        help="Additional trace corpus/canary root for admission. Current task run and rolling corpus are also scanned.",
    )
    parser.add_argument(
        "--admission_corpus_root",
        default="analysis_outputs/offline_trigger_corpus",
        help="Rolling corpus root used when --admission_scan_root is omitted.",
    )
    parser.add_argument("--admission_max_corpus_runs", type=int, default=8)
    parser.add_argument("--admission_out_dir", default="", help="Default: <out_dir>/taskXX/admission_wN")
    parser.add_argument(
        "--admission_allow_missing_scan",
        action="store_true",
        help="Do not fail admission if no scan root is available.",
    )
    parser.add_argument("--admission_no_hints", action="store_true")
    parser.add_argument("--admission_predicate_registry", default="")
    parser.add_argument("--admission_predicate_adapter", default="")
    parser.add_argument("--admission_diagnostic_signal_registry", default="")
    parser.add_argument("--admission_diagnostic_signal_statuses", default="")
    parser.add_argument("--admission_diagnostic_provider_root", action="append", default=[])
    parser.add_argument("--max_writes_per_task", type=int, default=5)
    parser.add_argument("--generated_benchmark_dir", default="")
    parser.add_argument("--generated_split", default="smoke", choices=["smoke", "train", "validation", "all"])
    parser.add_argument("--generated_smoke_run_dir", default="")
    parser.add_argument("--require_generated_smoke", action="store_true")
    parser.add_argument("--generated_smoke_min_episodes_per_task", type=int, default=1)
    parser.add_argument("--generated_smoke_no_video", action="store_true")
    return parser.parse_args()


def _clip(text: object, limit: int = 200) -> str:
    value = " ".join(str(text if text is not None else "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _bullet_block(items: object, *, limit: int = 5) -> list[str]:
    values = [str(item) for item in list(items or [])]
    lines = [f"  - {_clip(item)}" for item in values[:limit]]
    if len(values) > limit:
        lines.append(f"  - ... {len(values) - limit} more")
    return lines


def _previous_verdict(out_dir: Path, *, max_writes: int = 0) -> str:
    """Summarise earlier rounds of the awaiting task for the next actor prompt.

    Every round starts a fresh actor process, so without this block it cannot
    know why the previous draft was rejected or what validation showed.
    """
    from experiments.robot.libero.skill_pipeline.mine import load_mine_state

    state = load_mine_state(Path(out_dir) / "mine_state.json")
    task_id = state.get("awaiting_task")
    if task_id is None:
        return ""
    entry = dict((state.get("tasks") or {}).get(str(int(task_id))) or {})
    attempts = list(entry.get("attempts") or [])
    code_admission = dict(entry.get("last_code_admission") or {})
    admission = dict(entry.get("last_admission") or {})
    invalid = entry.get("last_invalid_validation")
    if not attempts and not code_admission and not admission and not invalid:
        return ""

    writes = int(entry.get("writes") or 0)
    lines = [
        "## Verdict on the previous rounds in this task",
        "",
        f"This would be write {writes + 1} of {max_writes} for task {int(task_id)}." if max_writes else
        f"This would be write {writes + 1} for task {int(task_id)}.",
        "",
    ]
    candidate_ids = [str(item) for item in (entry.get("candidate_skill_ids") or [])]
    bundle_id = str(entry.get("candidate_bundle_id") or "")
    if candidate_ids or bundle_id:
        lines.append("- last ingested candidate skills: " + (", ".join(candidate_ids[:8]) or "(none)"))
        if bundle_id:
            lines.append(f"- last ingested bundle id: {_clip(bundle_id)}")
        draft_files = [str(item) for item in (entry.get("candidate_skill_paths") or [])]
        lines.append("- draft files: " + (", ".join(draft_files[:8]) or "(unknown)"))
        lines.append("")
    for attempt in attempts:
        triage = dict(attempt.get("triage") or {})
        lines.append(f"### Round {int(attempt.get('writes') or 0)}")
        lines.append(
            f"- same-init validation: {attempt.get('on_success')}/{attempt.get('n_pairs')} "
            f"({float(attempt.get('success_rate') or 0.0):.2f}) with skills on, baseline "
            f"{attempt.get('off_success')}/{attempt.get('n_pairs')}"
        )
        if attempt.get("reason"):
            lines.append(f"- scored reason: {_clip(attempt.get('reason'))}")
        if attempt.get("regressed"):
            lines.append("- this write regressed against its own baseline")
        if attempt.get("unhit_fail_ids"):
            unhit = [str(item) for item in attempt["unhit_fail_ids"][:6]]
            lines.append("- failures where no skill fired at all: " + ", ".join(unhit))
        if triage:
            lines.append(
                f"- triage: {triage.get('status')} / {triage.get('primary_signature')} -- {_clip(triage.get('reason'))}"
            )
            if triage.get("recommended_next_action"):
                lines.append(f"- recommended next action: {_clip(triage.get('recommended_next_action'), 300)}")
        lines.append("")
    if code_admission:
        lines.append("### Last code admission: " + ("passed" if code_admission.get("ok") else "FAILED"))
        lines.extend(_bullet_block(code_admission.get("errors")))
        lines.append("")
    if admission:
        lines.append("### Last offline admission: " + ("passed" if admission.get("ok") else "FAILED"))
        lines.extend(_bullet_block(admission.get("errors")))
        lines.append("")
    if isinstance(invalid, dict):
        lines.append("### Last validation run could not be scored")
        lines.extend(_bullet_block(invalid.get("errors")))
        if invalid.get("reason"):
            lines.append(f"  - {_clip(invalid.get('reason'))}")
        lines.append("")
    lines.append(
        "Do not resubmit the same draft. An unregistered-id error means the id is "
        "missing from the named registry in the table above. An unchanged success "
        "rate alone does not identify the cause: verify runtime loading and compare "
        "the affected failure stages before rejecting a hypothesis."
    )
    return "\n".join(lines)


def _write_prompt_if_needed(
    result: dict,
    skills_dir: Path,
    out_dir: Path | None = None,
    *,
    max_writes: int = 0,
) -> dict:
    evidence_json = result.get("evidence_json") or result.get("pack_json")
    if result.get("status") != "need_draft" or not evidence_json:
        return result
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_codex_actor import render_actor_prompt

    extra = ""
    if out_dir is not None:
        try:
            extra = _previous_verdict(Path(out_dir), max_writes=int(max_writes or 0))
        except Exception as exc:  # a broken verdict must not block the actor prompt
            extra = f"## Verdict on the previous rounds in this task\n\n(unavailable: {type(exc).__name__}: {exc})"
    evidence_path = Path(evidence_json)
    prompt = render_actor_prompt(evidence_path.read_text(encoding="utf-8"), skills_dir, extra=extra)
    prompt_path = evidence_path.parent / "actor_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    result["evidence_json"] = str(evidence_path)
    result["actor_prompt"] = str(prompt_path)
    result.setdefault(
        "message",
        "Run the offline Codex actor on actor_prompt.md, then ingest draft.md or bundle.yaml.",
    )
    return result


def main() -> None:
    args = parse_args()
    repo = _repo_root()
    sys.path.insert(0, str(repo))
    from experiments.robot.libero.skill_pipeline.mine import (
        discover_task_ids,
        discover_task_ids_from_generated_run,
        ingest_mine_draft,
        load_mine_state,
        parse_task_ids,
        score_mine,
        step_mine,
    )
    from experiments.robot.libero.skill_pipeline.cli_config import (
        diagnostic_provider_roots_for_cli,
        diagnostic_signal_statuses_for_cli,
    )
    from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_config

    skill_config = resolve_skill_config(
        skill_pack=args.skill_pack or None,
        skills_dir=args.skills_dir or None,
        capability_registry=args.capability_registry or None,
        predicate_registry=args.admission_predicate_registry or None,
        predicate_adapter=args.admission_predicate_adapter or None,
        diagnostic_signal_registry=args.admission_diagnostic_signal_registry or None,
        repo=repo,
    )
    skills_dir = skill_config.skills_dir
    capability_registry = str(skill_config.capability_registry) if skill_config.capability_registry else None
    admission_diagnostic_statuses = diagnostic_signal_statuses_for_cli(
        skill_config,
        args.admission_diagnostic_signal_statuses,
        explicit_registry=bool(args.admission_diagnostic_signal_registry),
    )
    out_dir = Path(args.out_dir)
    run_dir = Path(args.run_dir)
    if args.task_ids.strip():
        task_ids = parse_task_ids(args.task_ids)
    elif args.generated_benchmark_dir:
        task_ids = discover_task_ids_from_generated_run(
            run_dir,
            generated_benchmark_dir=args.generated_benchmark_dir,
            generated_split=args.generated_split,
        )
    else:
        task_ids = discover_task_ids(run_dir)
    if not task_ids:
        raise SystemExit(f"no taskXX directories in {run_dir}")

    if args.command == "status":
        print(json.dumps(load_mine_state(out_dir / "mine_state.json"), ensure_ascii=False, indent=2))
        return

    if args.command == "ingest":
        if sum(bool(item) for item in (args.draft_md, args.bundle_yaml, args.draft_dir)) != 1:
            raise SystemExit("ingest requires exactly one of --draft_md, --bundle_yaml, or --draft_dir")
        result = ingest_mine_draft(
            draft_md=args.draft_md or None,
            bundle_yaml=args.bundle_yaml or None,
            draft_dir=args.draft_dir or None,
            run_dir=run_dir,
            skills_root=skills_dir,
            out_dir=out_dir,
            task_id=args.task_id or None,
            code_admission_gate=bool(args.enable_code_admission_gate or args.code_manifest),
            code_manifest=args.code_manifest or None,
            code_base_ref=args.code_base_ref,
            code_base_file_texts=(json.loads(Path(args.code_base_snapshot).read_text(encoding="utf-8"))
                                  if args.code_base_snapshot else None),
            code_admission_out_dir=args.code_admission_out_dir or None,
            admission_gate=bool(args.enable_admission_gate),
            admission_scan_roots=args.admission_scan_root,
            admission_corpus_root=args.admission_corpus_root,
            admission_max_corpus_runs=int(args.admission_max_corpus_runs),
            admission_out_dir=args.admission_out_dir or None,
            admission_require_offline_scan=not bool(args.admission_allow_missing_scan),
            admission_include_hints=not bool(args.admission_no_hints),
            max_writes_per_task=int(args.max_writes_per_task),
            generated_benchmark_dir=args.generated_benchmark_dir or None,
            generated_split=args.generated_split,
            generated_smoke_run_dir=args.generated_smoke_run_dir or None,
            require_generated_smoke=bool(args.require_generated_smoke),
            generated_smoke_min_episodes_per_task=int(args.generated_smoke_min_episodes_per_task),
            generated_smoke_require_video=not bool(args.generated_smoke_no_video),
            capability_registry=capability_registry,
            predicate_registry=str(skill_config.predicate_registry) if skill_config.predicate_registry else None,
            predicate_adapter=str(skill_config.predicate_adapter) if skill_config.predicate_adapter else None,
            diagnostic_signal_registry=str(skill_config.diagnostic_signal_registry)
            if skill_config.diagnostic_signal_registry
            else None,
            diagnostic_signal_statuses=admission_diagnostic_statuses,
            diagnostic_provider_roots=diagnostic_provider_roots_for_cli(
                skill_config,
                args.admission_diagnostic_provider_root,
            ),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit("ingest rejected: " + "; ".join(result.get("errors") or []))
        return

    if args.command == "score":
        if not args.on_dir:
            raise SystemExit("score requires --on_dir")
        result = score_mine(
            run_dir=run_dir,
            skills_root=skills_dir,
            out_dir=out_dir,
            on_dir=args.on_dir,
            task_id=args.task_id or None,
            generated_benchmark_dir=args.generated_benchmark_dir or None,
            generated_split=args.generated_split,
            max_writes_per_task=int(args.max_writes_per_task),
        )
        result = _write_prompt_if_needed(result, skills_dir, out_dir, max_writes=int(args.max_writes_per_task))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "need_draft":
            return
        if not result.get("ok") and result.get("status") not in {
            "invalid_validation",
            "write_budget_exhausted",
            "passed",
        }:
            raise SystemExit(result.get("reason") or "score failed")
        return

    result = step_mine(
        run_dir=run_dir,
        skills_root=skills_dir,
        out_dir=out_dir,
        task_ids=task_ids,
        generated_benchmark_dir=args.generated_benchmark_dir or None,
        generated_split=args.generated_split,
        capability_registry=capability_registry,
        max_writes_per_task=int(args.max_writes_per_task),
    )
    result = _write_prompt_if_needed(result, skills_dir, out_dir, max_writes=int(args.max_writes_per_task))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
