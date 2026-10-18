"""Count every selected case and classify its first observed recovery blocker.

This reports observed pipeline stages, not causal attribution or population
success rates. Missing later artifacts mean untested stages, not passed stages.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

STAGES = {
    "success": "完整成功", "pending": "尚未完成",
    "reference_collection": "真值复跑/入口采集", "initial_state": "初始本体状态",
    "language": "任务语言解析", "detection": "检测候选缺失",
    "binding": "实例/属性绑定", "geometry_support": "几何类型未支持",
    "geometry_fit": "RGB-D几何拟合", "planning": "求解/运动规划",
    "execution_tracking": "执行中视觉跟踪", "execution_state": "抓取/放置状态检查",
    "goal_verification": "完成判据不一致", "replan_interface": "重规划接口",
    "runtime_interface": "运行接口/其他异常",
}


def classify_artifacts(*, replay=None, failure=None, binding=None, logs="", solver=None,
                       visual_exit=None, collection_status=None):
    if visual_exit is None and collection_status != "not_run_no_recovery_fixture":
        return "pending", "等待本轮视觉进程结束"
    if replay is not None:
        if replay.get("recovery_success") and replay.get("final_simulator_success_for_evaluation"):
            return "success", "恢复判据与独立仿真评测均成功"
        if replay.get("recovery_success"):
            return "goal_verification", "恢复声称成功，但独立评测未成功或缺失"
    text = logs + "\n" + json.dumps(failure or {}, ensure_ascii=False)
    if "open gripper command reconstruction requires measured open fingers" in text:
        return "initial_state", "入口夹爪未满足测量张开条件"
    if "unsupported task language" in text or "unsupported object phrase" in text or "conflicting descriptions for category" in text or "unsupported visual goal" in text:
        return "language", "当前语言解析器不支持该任务表达"
    if binding and binding.get("status") == "refused":
        reason = binding.get("reason", "unknown")
        if reason in {"target_not_observed", "goal_not_observed", "reference_not_observed"}:
            return "detection", reason
        return "binding", reason
    if "bottle fitting requires a visually nominated bottle" in text or "plate fitting requires a visually nominated plate" in text:
        return "geometry_support", "当前形状提供器只支持bottle目标/plate支撑"
    if "current RGB-D bottle tracking unresolved" in text or "current bottle appearance association ambiguous" in text:
        return "execution_tracking", "当前深度/外观不足以接受瓶子位姿"
    if "anchor visual ID scene requires a current nomination snapshot" in text:
        return "replan_interface", "重新感知仍绑定首个求解快照"
    if "unexpected descriptor in anchor diagnostic" in text:
        return "binding", "任务属性不在受控案例的已确认范围"
    if solver is not None and not solver.get("feasible"):
        return "planning", str(solver.get("failure_reason") or "未得到可行计划")
    if any(word in text for word in ("insufficient bottle", "insufficient plate", "plate support is", "bottle depth", "support footprint", "no depth-connected", "upright bottle", "insufficient upright")):
        return "geometry_fit", "当前深度未通过形状拟合要求"
    if replay is not None:
        return "execution_state", str(replay.get("abort_reason") or "恢复判据未通过")
    if collection_status == "not_run_no_recovery_fixture":
        return "reference_collection", "本轮未取得恢复入口，视觉阶段未运行"
    if visual_exit is None and failure is None:
        return "pending", "等待本轮视觉结果"
    return "runtime_interface", str((failure or {}).get("error") or "见运行日志")[:240]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def summarize(batch):
    records = read_json(batch / "batch_results.json")
    if records is None:
        raise ValueError("batch_results.json missing; batch has not initialized")
    rows = []
    for rec in records:
        case = batch / rec["label"]
        visual = case / "visual"
        bindings = sorted(visual.glob("visual_nomination_step*/recovery01/pre_solver_attempt01/agentview/binding.json"))
        binding = read_json(bindings[-1]) if bindings else None
        solvers = sorted((visual / "cutamp_debug").glob("*.result.json"))
        solver = read_json(solvers[-1]) if solvers else None
        replay, failure = read_json(visual / "replay_result.json"), read_json(visual / "failure_result.json")
        exit_path = visual / "exitcode.txt"
        exitcode = int(exit_path.read_text().strip()) if exit_path.exists() else None
        logs = "\n".join(p.read_text(errors="replace") for p in
                         [visual / "driver.log", *visual.glob("visual_nomination_step*.log")] if p.exists())
        stage, reason = classify_artifacts(replay=replay, failure=failure, binding=binding, logs=logs,
            solver=solver, visual_exit=exitcode, collection_status=rec.get("visual_run", {}).get("status"))
        row = dict(label=rec["label"], suite=rec["suite"], task=rec["task_1based"],
            episode=rec["episode_idx"], seed=rec["seed"], init=rec["init_state_idx"], language=rec["language"],
            oracle_success=rec.get("oracle_run", {}).get("success"),
            oracle_exit=rec.get("oracle_run", {}).get("exitcode"),
            oracle_recovery_calls=rec.get("oracle_run", {}).get("recovery_calls"),
            stage=stage, stage_name=STAGES[stage], reason=reason,
            visual_exit=exitcode,
            visual_report={k:v for k,v in (replay or failure or {}).items() if k != "attempts"},
            visual_report_artifact=f"{rec['label']}/visual/" + ("replay_result.json" if replay else "failure_result.json"),
            binding=binding, solver_feasible=None if solver is None else solver.get("feasible"),
            solver_num_satisfying=None if solver is None else solver.get("num_satisfying"),
            runtime_state_count=len(list((visual / "visual_execution").glob("*.json"))))
        row["stage_artifacts"] = dict(
            visual_scene_available=bool(list(visual.glob("visual_nomination_step*/recovery01/pre_solver_attempt01/agentview/visual_scene.json"))),
            binding_candidate_present=bool(binding and binding.get("target_id") and binding.get("goal_id")),
            bottle_geometry_available=bool(list(visual.glob("visual_nomination_step*/recovery01/pre_solver_attempt01/agentview/bottle_model.json"))),
            plate_geometry_available=bool(list(visual.glob("visual_nomination_step*/recovery01/pre_solver_attempt01/agentview/plate_model.json"))),
            native_problem_available=bool(list((visual / "cutamp_debug").glob("*.problem.json"))),
            native_feasible=bool(solver and solver.get("feasible")),
        )
        oracle_errors = []
        for trace in (case / "oracle/run").glob("task*/ep*/recovery_trace.jsonl"):
            for line in trace.read_text().splitlines():
                if not line.strip():
                    continue
                error = json.loads(line).get("error")
                if error and error != "goal_atoms_not_yet_satisfied" and error not in oracle_errors:
                    oracle_errors.append(error)
        row["oracle_execution_error_codes"] = oracle_errors
        oracle_solutions = [read_json(f) for f in (case / "oracle/cutamp_debug").glob("*.result.json")]
        row["oracle_feasible_plan_count"] = sum(bool(result and result.get("feasible")) for result in oracle_solutions)
        rows.append(row)
    counts = Counter(row["stage"] for row in rows)
    complete = sum(row["stage"] != "pending" for row in rows)
    comparable = [row for row in rows if row["oracle_success"] is True and row["stage"] != "pending"]
    comparable_counts = Counter(row["stage"] for row in comparable)
    return dict(selected_task_count=len(rows), completed_task_count=complete,
        pending_task_count=len(rows) - complete, visual_success_count=counts["success"],
        visual_failure_or_unavailable_count=complete-counts["success"],
        oracle_success_count=sum(row["oracle_success"] is True for row in rows),
        stage_artifact_counts={key: sum(row["stage_artifacts"][key] for row in rows)
                               for key in rows[0]["stage_artifacts"]} if rows else {},
        first_blocker_counts={stage: count for stage, count in counts.items() if stage not in {"success", "pending"}},
        current_oracle_success_subset=dict(completed_task_count=len(comparable),
            visual_success_count=comparable_counts["success"],
            first_blocker_counts={stage:count for stage,count in comparable_counts.items() if stage!="success"}),
        first_blocker_names={stage: STAGES[stage] for stage in counts}, rows=rows,
        scope="fixed historically successful selection; one seed/init per task; not a general benchmark estimate")


def write_outputs(report, out):
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    columns = ["label", "suite", "task", "episode", "seed", "init", "language", "oracle_success", "stage_name", "reason", "visual_exit", "solver_feasible", "runtime_state_count"]
    with (out / "task_blockers.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader(); writer.writerows(report["rows"])
    lines = ["# RGB-D task批次：首个可观察卡点", "", f"任务数 {report['selected_task_count']}；完成 {report['completed_task_count']}；视觉完整成功 {report['visual_success_count']}；真值成功 {report['oracle_success_count']}。", "", "| Task | Seed/init | 真值成功 | RGB-D结果/首个卡点 |", "| --- | --- | --- | --- |"]
    for row in report["rows"]:
        lines.append(f"| {row['suite']} T{row['task']} | {row['seed']}/{row['init']} | {row['oracle_success']} | {row['stage_name']}：{row['reason'].replace('|', '/')} |")
    lines += ["", "每个失败样例只计首个有证据的阻塞点；后续阶段未测试。保留全部选定任务，不按结果删样本。"]
    (out / "task_blockers.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.batch)
    write_outputs(report, args.out_dir)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False))

if __name__ == "__main__": main()
