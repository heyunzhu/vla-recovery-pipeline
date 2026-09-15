from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .collector import summarize_run, write_summary
from .gates import evaluate_gates


def render_markdown(summary: dict[str, Any], gate_result: dict[str, Any] | None = None) -> str:
    overall = summary.get("overall") or {}
    lines = [
        "# Harness Report",
        "",
        f"Run: `{summary.get('run_dir', '')}`",
        "",
        "## Overall",
        "",
        "| episodes | success | success_rate | recovery_calls | videos | annotated_videos |",
        "|---:|---:|---:|---:|---:|---:|",
        (
            f"| {overall.get('episodes', 0)} | {overall.get('success', 0)} | "
            f"{float(overall.get('success_rate') or 0.0):.3f} | {overall.get('recovery_calls', 0)} | "
            f"{overall.get('videos', 0)} | {overall.get('annotated_videos', 0)} |"
        ),
        "",
    ]
    if gate_result is not None:
        lines.extend(
            [
                "## Gates",
                "",
                f"Status: `{gate_result.get('status', 'unknown')}`",
                "",
            ]
        )
        for failure in gate_result.get("failures") or []:
            lines.append(f"- FAIL: {failure}")
        for warning in gate_result.get("warnings") or []:
            lines.append(f"- WARN: {warning}")
        if not gate_result.get("failures") and not gate_result.get("warnings"):
            lines.append("- No gate failures or warnings.")
        lines.append("")

    lines.extend(["## Per Task", "", "| task | success | success_rate | recovery_calls | skill episodes |", "|---|---:|---:|---:|---|"])
    for row in summary.get("tasks") or []:
        skill_counts = ", ".join(f"{key}:{value}" for key, value in (row.get("skill_episode_counts") or {}).items())
        lines.append(
            f"| {row.get('task')} | {row.get('success', 0)}/{row.get('episodes', 0)} | "
            f"{float(row.get('success_rate') or 0.0):.3f} | {row.get('recovery_calls', 0)} | "
            f"{skill_counts or '-'} |"
        )
    lines.extend(["", "## Per Lane", "", "| lane | exit | success | success_rate | videos | annotated |", "|---|---:|---:|---:|---:|---:|"])
    for lane in summary.get("lanes") or []:
        lines.append(
            f"| `{lane.get('name')}` | {lane.get('exit_code') if lane.get('exit_code') is not None else '-'} | "
            f"{lane.get('success', 0)}/{lane.get('episodes', 0)} | {float(lane.get('success_rate') or 0.0):.3f} | "
            f"{lane.get('videos', 0)} | {lane.get('annotated_videos', 0)} |"
        )
    return "\n".join(lines) + "\n"


def write_report(run_dir: str | Path, *, gates: dict[str, Any] | None = None) -> dict[str, str]:
    root = Path(run_dir)
    summary = summarize_run(root)
    summary_path = write_summary(root, summary)
    gate_result = evaluate_gates(summary, gates if gates is not None else _load_spec_gates(root))
    gate_path = root / "harness_gates.json"
    gate_path.write_text(json.dumps(gate_result, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = root / "harness_report.md"
    report_path.write_text(render_markdown(summary, gate_result), encoding="utf-8")
    return {
        "summary_json": str(summary_path),
        "gates_json": str(gate_path),
        "report_md": str(report_path),
    }


def _load_spec_gates(run_dir: Path) -> dict[str, Any]:
    spec_path = run_dir / "resolved_spec.json"
    if not spec_path.exists():
        return {}
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    gates = spec.get("gates") or {}
    return gates if isinstance(gates, dict) else {}
