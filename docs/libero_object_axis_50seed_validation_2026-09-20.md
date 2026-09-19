# object 轴 50-seed 验证轮（seeds 1–50）：结果、触发覆盖与执行层证据

日期：2026-09-20
范围：`libero_object_swap` + `libero_object_task` 两条轴，seeds 1–50（每 task 50 集，共 1000 集），
带 mining 工作包（32 条 skill）。本文件只记录**验证结果**与随之暴露的问题；修复工作交给 codex 在 dev 集（seeds 51–65）上做。

## 1. 运行配置与 provenance

| 项 | 值 |
| --- | --- |
| skill pack | `$WORK/logs/object_50seed_20260920/pack`（`skills/_index.yaml` md5 **`714e331697d751864fb28875c4cfaa95`**，32 条） |
| pack 名 | `libero_object_task_from_spatial_swap_mining_base_20260918` |
| 参数 | `episode_seed_start=1`、`num_trials_per_task=50`、`max_recovery_calls=2`、`enable_mining_skills=true`、`enable_skills=false`、`seed=90`、`save_video=true` |
| policy | `$WORK/models/pi0_libero_openpi` |
| swap run root | `$WORK/logs/object_50seed_20260920/libero_object_swap/object_swap_seed1_50_mrs200` |
| task run root | `$WORK/logs/object_50seed_20260920/libero_object_task/object_task_seed1_50_mrs200` |
| 运行时长 | swap 2026-09-19 16:47:37Z → 22:30:17Z（约 5h43m / 500 集）；task 17:59:38Z → 22:53:49Z（约 4h54m） |
| 仓库版本 | `3bfdf0b`（第二个 50-seed 轮次 skill 已合入包） |

## 2. 结果

### 2.1 `libero_object_swap`：354/500 = **0.708**

| task | 物体 | 成功/50 | 有 recovery 的集数 | plain 成功 | recovery 集里成功 |
| --- | --- | ---: | ---: | ---: | ---: |
| t01 | alphabet soup | 50 | 50 | 0 | 50 |
| t02 | cream cheese | 40 | 45 | 0 | 40 |
| t03 | salad dressing | 48 | 50 | 0 | 48 |
| t04 | bbq sauce | 49 | 50 | 0 | 49 |
| t05 | ketchup | 47 | 50 | 0 | 47 |
| t06 | tomato sauce | 49 | 50 | 0 | 49 |
| t07 | butter | 33 | 50 | 0 | 33 |
| t08 | **milk** | **0** | 50 | 0 | 0 |
| t09 | chocolate pudding | 38 | 50 | 0 | 38 |
| t10 | **orange juice** | **0** | 50 | 0 | 0 |

### 2.2 `libero_object_task`：338/500 = **0.676**

| task | 物体 | 成功/50 | 有 recovery 的集数 | plain 成功 | recovery 集里成功 |
| --- | --- | ---: | ---: | ---: | ---: |
| t01 | cream cheese | 26 | 26 | 0 | 26 |
| t02 | alphabet soup | 49 | 0 | 49 | 0 |
| t03 | tomato sauce | 42 | 49 | 0 | 42 |
| t04 | ketchup | 50 | 50 | 0 | 50 |
| t05 | **milk** | **0** | 50 | 0 | 0 |
| t06 | bbq sauce | 50 | 50 | 0 | 50 |
| t07 | **orange juice** | **0** | 49 | 0 | 0 |
| t08 | butter | 25 | 50 | 0 | 25 |
| t09 | salad dressing | 49 | 50 | 0 | 49 |
| t10 | chocolate pudding | 47 | 50 | 0 | 47 |

### 2.3 按物体合并（两条轴各 50 集）

| 物体 | swap | task | 合计 | 判定 |
| --- | ---: | ---: | ---: | --- |
| alphabet soup | 50/50 | 49/50 | **99/100** | 达标 |
| bbq sauce | 49/50 | 50/50 | **99/100** | 达标 |
| ketchup | 47/50 | 50/50 | **97/100** | 达标 |
| salad dressing | 48/50 | 49/50 | **97/100** | 达标 |
| tomato sauce | 49/50 | 42/50 | **91/100** | 达标 |
| chocolate pudding | 38/50 | 47/50 | **85/100** | 偏弱 |
| cream cheese | 40/50 | 26/50 | **66/100** | 偏弱（触发覆盖只有 71/100） |
| butter | 33/50 | 25/50 | **58/100** | 明显不达标 |
| **milk** | **0/50** | **0/50** | **0/100** | **完全失败** |
| **orange juice** | **0/50** | **0/50** | **0/100** | **完全失败** |

## 3. 触发层：这三类物体的失败**不再是"没触发"**

触发规则覆盖的集数（`kind=rule` 事件，按 skill 聚合）：

| skill | swap 集数 | task 集数 |
| --- | ---: | ---: |
| `object_basket_persistent_wrong_intent_group_a` | 250 | 200 |
| `object_basket_bbq_orange_precontact_wrong_intent` | 100 | 99 |
| `object_basket_salad_dressing_precontact_wrong_intent` | 50 | 50 |
| `object_basket_tomato_persistent_wrong_intent` | 50 | 9 |
| `object_basket_cream_cheese_precontact_wrong_intent` | 40 | 0 |
| `object_basket_cream_tomato_q5_wrong_intent_window` | 5 | 68 |

- butter / milk / orange juice：**两条轴上每个 task 的 50 集里都有 49–50 集进入了 recovery**。
- 触发层仍然漏的是 **cream cheese**：swap 45/50、task 只有 26/50（task 轴 26 集触发、26 集成功，等于"不触发就必失败"）。
- task 轴 t02 alphabet soup 是唯一 0 触发的 task，并且 49/50 靠 VLA 本身完成。

`recovery_calls` 分布：swap `{0:5, 1:388, 2:107}`；task `{0:76, 1:308, 2:116}`——即约 1/5 的集数把两次预算都用完了。

## 4. 执行层：segment 层"成功"与 task 层失败之间的落差

`kind=trajectory` 段统计（executed / segment 层 success）：

| skill | swap | task |
| --- | --- | --- |
| `object_basket_persistent_wrong_intent_group_a` | 1090 / 1033 | 953 / 850 |
| `object_basket_bbq_orange_precontact_wrong_intent` | 260 / 248 | 250 / 250 |
| `object_basket_salad_dressing_precontact_wrong_intent` | 250 / 250 | 257 / 245 |
| `object_basket_tomato_persistent_wrong_intent` | 256 / 235 | 61 / 49 |
| `object_basket_cream_cheese_precontact_wrong_intent` | 219 / 135 | —（未触发） |
| `object_basket_cream_tomato_q5_wrong_intent_window` | 26 / 20 | 387 / 309 |

- `goal_check` 失败全部是 `goal_atoms_not_yet_satisfied`（swap 1592 次、task 1393 次），其中失败检查项绝大多数是
  `object_near_surface_and_released`（swap n=1497，`xy_dist` 0.203–0.536 m、均值 0.425；task n=1392，0.231–0.514、均值 0.343）。
  **注意**：这些多数发生在 `__start__`（目标还没被搬动时的初检），xy 距离大是正常的，不能当作失败信号；
  要看的是 recovery **结束之后**的状态。
- 结论性落差：`persistent_wrong_intent_group_a` 在 swap 上 segment 层 1033/1090 成功，但 milk/orange juice 的 task 层成功率为 0。
  "段成功"不等于"目标达成"，这段落差（拿起来了但没真拿住／放下去了但不在 contain region／放好后又被 VLA 弄掉）就是下一步的诊断重点。
- `abort_episode` 全 0，没有 episode 因 abort 提前结束。

## 5. 对照基线（重要：之前引用的 0.68 不能用来对比这两个变体）

- **同一套扰动变体的 VLA-only 基线**（`$WORK/logs/libero_screening_20260918`，seeds 51–65，每 task 15 集，
  baseline 与 W0 两个条件，recovery 调用数为 **0**）：
  - `libero_object_swap`：baseline **0/147**、w0 **0/148**（合计 **0/295**）
  - `libero_object_task`：baseline **14/148**、w0 **14/150**（合计 **14/298**，全部来自 t02 alphabet soup 的 14/15）
- 即：在这两个扰动变体上，**VLA 自身几乎不能成功**（swap 全 0；task 只有 alphabet soup 能成）。
  带 skill 的 50-seed 结果是 swap 0.708 / task 0.676，说明恢复路径承担了几乎所有成功；
  因此 milk / orange juice 的 0/100 不是"被 skill 弄坏了"，而是**恢复路径对这两个物体从来没成功过**。
- 2026-09-04 的 `rlinf_four_suits_baseline_20260904_10ep_video_v1` 里 `libero_object` 68/100（milk 2/10、orange juice 2/10、
  butter 5/10）跑的是**原始 LIBERO `libero_object` suite**，任务实例与这两个变体不同，**不可直接对比**，仅作历史参考。
- **缺口**：还没有"同 seeds 1–50、关掉 mining skills"的消融。若需要把"恢复路径贡献"写成硬结论，需要补这条 500×2 集的消融
  （估约 5h/轴/单卡）。已在等待用户确认后再排。

## 6. 异常与待解问题

1. **milk / orange juice 0/100**：触发 100%，两次 recovery 预算多数用完，segment 层大量"成功"，task 层恒 0。
   第 2 轮的 `grasp_object_basket_tall_carton_topdown_deep` hint 在 50 集尺度上没有产生任何可测收益。
2. **butter 58/100**：两条轴都不达标但也不是 0；此前 codex 的执行层诊断（flat box 24 个候选、9/9 planner feasible、
   闭合后失去双边接触）与本次"segment 成功但 task 失败"的落差一致。
3. **cream cheese 触发覆盖只有 71/100**（task 轴 26/50、swap 轴 45/50），是触发层唯一还有明显空间的物体；
   它也是 task 轴最弱的非零 task（26/50）。
4. `object_near_surface_and_released` 的 xy 统计在 `__start__` 上本就很大，后续报告不要把它当失败信号。

## 7. 下一步

- 已把本节全部数字（含**更正后的 swap 物体↔task 映射**）通过 codex bridge 发给你（消息 `0039`、更正 `0040`），
  并明确：**seeds 1–50 是测试集，禁止在其上开发/调参**，诊断与候选只能在 dev seeds 51–65 上做。
- 待 codex 在 dev 集上给出：分层诊断（触发/抓取/放置）、skill 候选 + 离线扫描、以及对 milk/orange juice 的修复方案。
- 待用户确认：是否补"同 seeds 1–50、关闭 mining skills"的消融，以把恢复路径的净贡献写成硬结论。

## 8. 本地产物与 md5

| 文件 | 说明 |
| --- | --- |
| `remote_outputs/object_50seed_20260920/export_50seed_meta.tar.gz` | 远端元数据包（2002 个文件），md5 **`dc0d83afb56e159bb0fc18006b7ab4f3`** |
| `remote_outputs/object_50seed_20260920/analysis/object_50seed_analysis.json` | 本文件全部数字的结构化版本 |
| `remote_outputs/object_50seed_20260920/analysis/object_50seed_analysis.md` | 同上的 markdown 表 |
| `openvla-oft/experiments/analyze_object_50seed.py` | 从 `summary.json` / `episode.json` / `recovery_trace.jsonl` 生成上述统计 |
| `openvla-oft/experiments/analyze_screening_dev.py` | dev 集（seeds 51–65）baseline/W0 逐 task 统计 |

未上传视频与 frames（各轴约 2.7 G，抽样看片段时再按需拉取）。
