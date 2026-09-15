# Diagnostic Signal Pipeline

更新日期：2026-09-01

本文定义 repair 写作过程中新增 runner 诊断信号的安全流程。诊断信号是比 skill
更底层的 artifact：它进入 qstate / trace，后续 repair trigger 可能依赖它。因此它不能由
Codex 在普通 repair 写作中顺手改主链路。

当前实现位置：

- `skill_packs/<pack>/diagnostics/registry.yaml`（active pack 可覆盖）
- `skill_packs/<pack>/code/` 或 pack 内其它受控路径（可放 pack-local provider 文件）
- `experiments/robot/libero/skill_pipeline/diagnostics/registry.yaml`（未指定 pack 时的默认 registry）
- `experiments/robot/libero/skill_pipeline/diagnostics/registry.py`
- `experiments/robot/libero/skill_pipeline/diagnostics/runtime.py`
- `experiments/robot/libero/skill_pipeline/diagnostics/providers/`
- `scripts/recovery/skill_pipeline/replay_diagnostic_signals.py`

registry 可以 pack-local。provider 可以是两种形式：

- 共享 provider：`experiments.robot.libero.skill_pipeline.diagnostics.providers.*`
- pack-local provider：registry 文件相对路径，且解析后必须位于 active pack root 下

也就是说，skill pack 可以选择启用哪些诊断信号，也可以携带自己的 draft / shadow provider；
但普通 task-specific skill 不应把 provider 私货散落到 runner、planner 或 executor 主流程。

## 1. 状态机

每个诊断信号必须登记在 registry 中。

| 状态 | 含义 |
| --- | --- |
| `draft` | agent 草稿，只能在离线 replay 或 mining validation 中显式启用。 |
| `shadow` | 可在 rollout 中记录，但不影响 repair matcher。 |
| `online` | 已通过测试，允许后续通过正式 predicate 暴露给 repair。 |
| `retired` | 已废弃，runtime 不再计算，新 skill 不得引用。 |

默认 runner 不启用任何诊断 signal。只有显式传入：

```bash
--diagnostic_signal_statuses shadow
```

才会计算 registry 中对应状态的 provider。
Harness YAML 也可以通过 `diagnostic_signals.enabled: true` 和
`diagnostic_signals.statuses: [shadow, online]` 打开它；runner 会优先使用 active skill pack 的
`diagnostic_signal_registry`。

## 2. Provider 约束

provider 必须是纯函数：

```python
def compute(state, history):
    return {
        "diag_example_v1": True,
        "diag_example_v1_score": 0.8,
    }
```

要求：

- provider 必须位于 `experiments.robot.libero.skill_pipeline.diagnostics.providers.*`，或作为
  文件路径位于 active skill pack root 下。
- 输出字段必须以 `diag_` 开头。
- 不得覆盖 qstate / query trace 的已有字段。
- 不得 step env、调用 planner、读取未来 rollout success、写全局状态。
- 异常会被记录在 `diagnostic_signals.errors`，不会中断 rollout。

## 3. Trace 记录

启用后，每条 `query_trace.jsonl` 会新增：

```json
{
  "diagnostic_signals": {
    "hook": "after_pi0_query",
    "active_statuses": ["shadow"],
    "values": {
      "diag_target_approach_window_v1": true,
      "diag_target_approach_window_v1_score": 0.93
    },
    "results": [],
    "errors": []
  }
}
```

这些值默认不会平铺进 qstate，也不会被现有 repair trigger 使用。这样可以先观察信号质量，
再决定是否晋升。

## 4. 离线 Replay

已有 `query_trace.jsonl` 可用 replay 脚本补算诊断信号：

```bash
python scripts/recovery/skill_pipeline/replay_diagnostic_signals.py \
  --query-trace /path/to/query_trace.jsonl \
  --out-jsonl /path/to/query_trace.with_diag.jsonl \
  --statuses shadow
```

replay 结果用于检查：

- 信号是否在失败 episode 的 `last_safe_query` 附近变 true；
- 是否在成功 episode 中乱响；
- 是否比已有 qstate 字段更接近视觉诊断；
- 是否有缺失 input 或 provider error。

## 5. 晋升条件

诊断信号从 `draft` / `shadow` 晋升到 `online` 前，必须满足：

1. registry schema 通过；
2. provider 单元测试覆盖 true / false / missing；
3. 历史 trace replay 有报告；
4. shadow rollout 只记录、不触发；
5. repair 静态 gate 确认没有宽泛误用；
6. 人工确认它的语义稳定。

晋升到 `online` 仍不等于直接触发 recovery。repair 若要使用它，需要单独在 predicate
registry / matcher 中暴露正式谓词，并通过 repair 静态测试。
