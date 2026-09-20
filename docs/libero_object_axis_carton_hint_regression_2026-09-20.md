# object 轴 carton 回归：round-2 的 tall-carton hint 已撤回

日期：2026-09-20
结论：`skills/fail_only/recovery_hint/grasp/grasp_object_basket_tall_carton_topdown_deep.md` **是纯回归**，
本次提交把它从工作包中撤回。工作包 `skills/_index.yaml` md5：`714e331697d751864fb28875c4cfaa95`（32 条）
→ **`b74de429c5e3688c7270dc1bdd376ae5`（31 条）**。

该 md5 与正在实例上做 50-seed 验证的 trial pack（`$WORK/logs/carton_revert_20260920/pack`）**逐字节一致**，
即"仓库里的包"与"被测的包"是同一个东西。

## 1. 症状（50-seed 验证，seeds 1–50）

`libero_object_swap` t08 / `libero_object_task` t05（milk）与 swap t10 / task t07（orange juice）
**共 100 集 0 成功**，且签名完全一致：`recovery_calls=2, num_queries=58, num_env_steps=280`，
而同一批 run 里其它物体都是 `q=6/7` 成功。

## 2. 失败发生在**规划层**，不是抓取层

`recovery_trace.jsonl`（例：`object_50seed_20260920/libero_object_task/object_task_seed1_50_mrs200/task05/ep00`）
只有 4 个事件，**0 个 `trajectory`**：

```
rule/  q=6  ok=True   skill=object_basket_persistent_wrong_intent_group_a
plan/  q=6  ok=False  label=real_cutamp_no_feasible_goal
           error="No satisfying particles found after optimizing all 1 plan(s)"
rule/  q=7  ok=True   skill=object_basket_persistent_wrong_intent_group_a
plan/  q=7  ok=False  label=real_cutamp_no_feasible_goal
```

这与 round-2 写该 hint 时的前提（"planner-feasible，只是 lift probe 的 `object_followed=false`"）**相反**。

## 3. 只有被 hint 命中的物体失败（dev 复现，seeds 51–55，当前包）

新跑 `$WORK/logs/object_dev_repro_20260920/`（当前包、与 09-19 trend 完全相同的参数与 task）：

| task | 物体 | 结果 |
| --- | --- | --- |
| `libero_object_task` t05 | milk | **0/5** |
| `libero_object_task` t07 | orange juice | **0/5** |
| `libero_object_task` t01 | cream cheese | 4/5 |
| `libero_object_task` t08 | butter | 4/5 |
| `libero_object_swap` t08 | milk | **0/5** |
| `libero_object_swap` t10 | orange juice | **0/5** |
| `libero_object_swap` t02 | cream cheese | 5/5 |
| `libero_object_swap` t07 | butter | 4/5 |

合计 swap 9/20、task 8/20；**失败的 20 集全部是纸盒**。这就排除了"dev seed 太难"的解释。

## 4. cuTAMP debug：hint 换上的 profile 就是 active sampler

`object_dev_repro_20260920/libero_object_swap/object_swap_carton_repro_seed51_55/cutamp_debug/` 最新一组：

```
diagnostics.grasp_sampler_profile = "cream_cheese_flat_box_topdown_deep_v1"
grasp_counts = {"orange_juice_1_main": 24, "basket_1_main": 24, ...}
result: feasible=false, num_satisfying=0, elapsed_sec=10.15
        failure_reason="No satisfying particles found after optimizing all 1 plan(s)"
        optimized_plan_present=false, plan_type=NoneType
        motiongen_start_limit_debug={"applied": false, "bounds_found": false}
```

## 5. 用包自己的采样器离线复算（CPU，无仿真）

`skill_packs/.../code/grasp_profiles.py` → `sample_grasp_profile("cream_cheese_flat_box_topdown_deep_v1", dims)`：

| 物体 | AABB (m) | 候选 | 夹爪开度 | 横向尺寸 | 单边余量 | 抓取点离桌面 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| milk / orange juice | 0.0525 × 0.0531 × **0.1312** | 24 | **0.0591** | 0.0525 | **0.0033** | 0.0426 m（盒高 0.1312） |
| cream cheese / butter | 0.080 × 0.055 × **0.020** | 24 | 0.0619 | 0.020 | 0.0209 | 0.0065 m（盒高 0.020） |

`profile_gripper_width = clip(2.25 × min(水平半轴), 0.025, 0.075)`：对小方盒留 2 cm 余量，
对细高盒只剩 3.3 mm/边；配合 `top_coords = [-0.35, -0.15] × top_half` 的深抓点，
24 个候选全部被判不可行。复算脚本：`openvla-oft/experiments/repro_carton_profile_geometry.py`。

## 6. A/B：删掉 hint 后 milk 立刻恢复（seeds 1–50，trial pack `b74de429`）

`$WORK/logs/codex_validation_cartonrevert/`，截至 2026-09-20 08:15（本地）：

| task | 物体 | 有 hint（正式验证） | 无 hint（本次 A/B，进行中） |
| --- | --- | ---: | ---: |
| `libero_object_task` t05 | milk | 0/50 | **10/12** |
| `libero_object_swap` t08 | milk | 0/50 | **6/11** |
| `libero_object_task` t07 | orange juice | 0/50 | 跑完补录 |
| `libero_object_swap` t10 | orange juice | 0/50 | 跑完补录 |

两个 lane 里 recovery 在**每一集**都被触发（`recovery_episodes == episodes`），说明增益来自"规划重新可行"，
而不是"触发变多了"。

## 7. 为什么 round-2 的准入没拦住它

- 该 hint 的证据是 **4 个 dev 失败集**（task05/ep03,ep04、task07/ep00,ep04），没有对照成功集；
- 离线扫描（`scan_skill_triggers.py`）衡量的是**作用域匹配**（命中/误触），**不检查规划可行性**，
  所以"60/60 命中、成功集 0 误触"与"候选不可行"可以同时成立；
- 没有"撤回对照"（ablation）：只要跑一次"同一 seeds、去掉该 skill"的 A/B 就能发现。

后续每个新 skill 一律要求：**失败集 + 对照集两侧数字**，且 grasp 类候选必须在 dev 上给出
plan 可行率与 segment 是否执行，而不只是作用域命中率。

## 8. 下一步

- codex 已产出候选 `grasp_object_basket_upright_carton_body_side_v1`（draft，
  `$WORK/logs/object_dev_layered_round_20260920/drafts/`）与 pack-local profile 提案
  `upright_carton_profile_change_proposal.md`；该 profile **尚未实现**，需要代码 + 静态测试 + dev A/B，
  属于独立的下一轮，不随本次撤回一起进包。
- 仍待处理：cream cheese 在 task 轴的触发覆盖缺口（26/50 触发、26/50 成功）；q5 窗口触发器在 1–50 上的验证。
- 本文件的 A/B 表格在 revert 两条 lane 跑完后补全（含 orange juice 与 50 集全量）。
