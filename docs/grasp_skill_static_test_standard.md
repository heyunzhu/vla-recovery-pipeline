# Grasp Skill Static Test Standard

更新日期：2026-09-09

本文定义 `grasp` recovery hint 的静态测试标准。它面向 harness / CI 使用，用来防止
Codex 在 mining loop 中写出匹配范围过宽、候选点不可解释、debug 候选和真实 cuTAMP
采样不一致，或把 grasp / grounding / geometry / place 职责混在一起的 skill。

本文只约束 active skill pack 下的：

```text
skill_packs/<pack>/skills/pair/recovery_hint/grasp/*.md
```

`grasp` 不决定是否进入 recovery。它只在某个 repair / trigger 已经决定进入 recovery 后，
选择抓取目标的采样 profile 和少量抓取安全相关 executor 参数。

## 1. 核心契约

`grasp` skill 只回答一个问题：

> 当前 recovery 要抓这个目标对象时，应该使用哪一组 grasp candidates / yaw / close / lift 设置？

因此静态测试检查五层契约：

1. **Catalog 契约**：在线 skill 必须显式出现在 active pack 的 `skills/_index.yaml`；
   退役草稿不能混在 pair grasp 目录里伪装成在线 skill。
2. **Schema 契约**：必须是 `kind: recovery_hint`、`scope: grasp`，不能声明 `trigger`、
   `hook` 或 `backend`。
3. **Scope 契约**：必须绑定目标对象类别，避免一个通用 regex 抢走特殊对象。
4. **Profile 契约**：`grasp_profile` 必须由 active pack 的 grasp adapter 实现，并能被
   problem/debug adapter 和 real cuTAMP adapter 同时消费。
5. **Evidence 契约**：必须能说明候选点来自哪批视频、trace、强制触发或 profile sweep。

## 2. Catalog 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | active pack `skills/_index.yaml` 中引用的 grasp skill 文件不存在。 |
| ERROR | active pack `skills/pair/recovery_hint/grasp/` 下存在未 online 且没有 `status: draft/retired/archived/experimental` 的 `.md` 文件。 |
| ERROR | online grasp skill 标记为 `status: draft/retired/archived/experimental`。 |
| WARN | 文件名、`id`、profile 名语义明显不一致。 |

文件存在不等于 online 生效。8 月 30 日后的 carton 例子就是这个问题：旧
`grasp_carton_body_vertical_deep.md` 被复制进评测快照，但没有出现在 `_index.yaml`，
也没有实际触发。静态 gate 要把这种“孤儿文件”显式拦出来。

## 3. Schema 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | `kind` 必须是 `recovery_hint`。 |
| ERROR | `scope` 必须是 `grasp`。 |
| ERROR | 不得声明 `trigger`、`hook`、`backend`。 |
| ERROR | 必须有 `recovery_hints.grasp_profile`。 |
| ERROR | `grasp_profile` 必须由 core grasp registry 或 active pack 的 grasp adapter 暴露，并在 active pack 的 `capabilities.yaml` 注册。 |
| WARN | `recovery_hints.target` 不是 `target` 时，需要人工确认。 |

## 4. Scope / Priority 检查

`grasp` 的高风险不是“不触发”，而是 recovery 已经触发后它错误覆盖了抓取 profile。

| 级别 | 检查项 |
| --- | --- |
| ERROR | 缺少 `target_name_matches`。 |
| ERROR | `target_name_matches` 是 `.*`、`.+` 这类过宽表达。 |
| ERROR | 只靠 `task_language_matches` 匹配。 |
| ERROR | generic bowl skill 没有排除 `white_bowl` / `white bowl`。 |
| ERROR | carton profile 缺少 `target_orientation_is: upright/fallen`。 |
| WARN | 宽目标 regex 没有 `target_name_excludes`。 |
| WARN | 多个 grasp skill 会同时匹配同一 canary，需要确认高 priority 的 winner 是有意设计。 |

当前 matcher 会按 priority 合并 recovery hint；对于 `grasp_profile` 这种 scalar，后合并的
高 priority skill 会覆盖低 priority skill。因此静态测试要维护 canary：

| canary | 预期 winner |
| --- | --- |
| black bowl 普通任务 | `grasp_bowl_rim_diagonal_mixed_topdown` |
| black bowl cabinet-top | `grasp_bowl_rim_away_from_open_drawer_topdown` |
| white bowl 普通 plate | `grasp_small_shallow_bowl_rim_diagonal_topdown` |
| white bowl right-of-plate task38 | `grasp_task38_white_bowl_microwave_high_lift` |
| cream cheese / butter / chocolate pudding | `grasp_flat_box_topdown_short_side_deep` |
| book | `grasp_book_upright_topdown` |
| alphabet soup can | `grasp_can_body_lower_side` |
| tomato sauce can | `grasp_tomato_sauce_can_body_orthogonal_lower` |
| milk upright | `grasp_carton_upright_body_side` |
| milk fallen | `grasp_carton_fallen_body_side` |
| mug / cup | `grasp_mug_body_side_avoid_handle` |
| moka pot | `grasp_moka_pot_handle_topdown` |

## 5. Profile 实现检查

所有 benchmark-specific 新 profile 必须写在 active skill pack adapter：

```text
skill_packs/<pack>/code/grasp_profiles.py
```

并同时通过：

- `sample_grasp_profile(...)`
- `sample_grasp_profile_xyzrpy(...)`
- `profile_gripper_width(...)`

`experiments/robot/libero/tiptop_repro/grasp_profiles.py` 只保留共享 bridge、registry 和默认
`libero_topdown` 等通用 profile。不要分别在 `tamp_scene.py` 和 `real_cutamp_backend.py` 里手写
两套逻辑，也不要把 LIBERO-90 特化 profile 塞回主流程。

静态 gate 要区分三层：

- core registry：主流程默认能采样的通用 profile，例如 `libero_topdown`；
- pack adapter：当前 benchmark / campaign 拥有的对象特化 profile；
- capability registry：当前 pack 允许 online skill 使用哪些 profile。

一个 profile 只有同时能实现、能被当前 pack 暴露、并被 capability registry 允许，才算可用。

静态测试要求：

| 级别 | 检查项 |
| --- | --- |
| ERROR | profile 不能 normalize。 |
| ERROR | `sample_grasp_profile` 返回空候选。 |
| ERROR | `sample_grasp_profile` 与 `sample_grasp_profile_xyzrpy` 候选数量不同。 |
| ERROR | 候选 xyz/rpy 出现 NaN 或 inf。 |
| ERROR | `profile_gripper_width` 超出 Panda gripper sanity range。 |
| WARN | 候选数量超过 64，除非有明确实验说明。 |
| WARN | skill 使用 `native` / `cutamp_native` profile，难以审计。 |

## 6. Executor 参数边界

grasp skill 可以带少量 executor 参数，但只能服务于 close / lift / confirmed-grasp transfer。

当前 allowlist：

| key | 合理范围 |
| --- | --- |
| `grasp_close_max_above_m` | 0.03 - 0.22 |
| `grasp_lift_probe_m` | 0.00 - 0.10 |
| `grasp_lift_probe_max_steps` | 0 - 60 |
| `grasp_lift_follow_m` | 0.001 - 0.08 |
| `place_hover_clearance_m` | 0.00 - 0.20 |
| `place_lift_min_clearance_m` | 0.00 - 0.15 |
| `place_lift_max_steps` | 0 - 80 |

| 级别 | 检查项 |
| --- | --- |
| ERROR | executor key 不在 allowlist。 |
| ERROR | executor value 不是数字。 |
| ERROR | executor value 超出执行器 clamp 范围。 |
| ERROR | grasp skill 中出现 `grounding_hints`、`geometry_hints`、`placement_region`、`placement_surface` 等跨职责字段。 |
| WARN | `params` 顶层出现 `source`、`executor` 以外的 key。 |

## 7. Trace Scan 检查

静态 gate 不重跑仿真，但可以用历史 `query_trace.jsonl` 扫描“如果 recovery 在这里触发，
会合并哪些 grasp hint”。

最低报告：

| 字段 | 含义 |
| --- | --- |
| `task_id` / `episode_idx` / `query_idx` | 发生匹配的位置。 |
| `target_name` / `target_orientation` | grasp scope 使用的对象状态。 |
| `matched_grasp_hints` | 所有匹配的 grasp hint。 |
| `winning_grasp_profile` | 最终进入 cuTAMP 的 profile。 |
| `overridden_profiles` | 被高 priority 覆盖的 profile。 |
| `success` | 该 episode 最终是否成功。 |

这个报告用于回答：新 skill 是否大面积误匹配历史成功 episode，是否抢走已验证稳定的
grasp profile。

## 8. 命令

当前静态 gate 入口：

```bash
python scripts/recovery/skill_pipeline/check_grasp_skills.py --skill_pack <pack>
```

输出 Markdown 报告：

```bash
python scripts/recovery/skill_pipeline/check_grasp_skills.py \
  --skill_pack <pack> \
  --md-out /tmp/grasp_static_gate_report.md \
  --json-out /tmp/grasp_static_gate_result.json
```

默认只有 ERROR 会让命令失败；如果希望 warning 也失败：

```bash
python scripts/recovery/skill_pipeline/check_grasp_skills.py --skill_pack <pack> --fail-on-warn
```

## 9. Gate 结果分级

| 级别 | 处理方式 |
| --- | --- |
| ERROR | 不允许 ingest / 不允许进入 `online:`。 |
| WARN | 可以保留草稿，但需要人工确认。 |
| INFO | 只写入报告。 |

建议 harness 产物：

- `grasp_static_gate_result.json`
- `grasp_static_gate_report.md`
- `grasp_canary_matches.csv`
- `grasp_trace_scan.csv`
