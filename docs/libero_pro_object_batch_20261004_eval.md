# object-swap 单轴改造 50-seed：pack vs 对照

日期：2026-10-04  
实例：启智 `xinghanbo-eval`（1×4090）  
日志：`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/pro_object_batch_20261004_mrs200/`

源轴是 LIBERO-Pro 的 `libero_object_swap`，不是底库 `libero_object`，也不是 `libero_object_task`。10 个 swap 布局各改一个轴，得到 30 条新任务，suite 名 `pro_object_batch_20261004_task`。评测命令与 `docs/libero_pro_run_pack_eval_2026-10-03.md` 相同：`--enable_mining_skills`，当前 36 条 fail_only object pack，真实 cuTAMP，`grasp_dof=6`，`--max_recovery_steps 200`，`--max_recovery_calls 2`，语言 bddl/bddl，不设 `--force_recovery_query`。对照关掉 skill 和 cuTAMP。每条 50 集，`episode_seed_start=1`，`seed=90`。

pack 1317/1500 = **0.878**。对照 136/1500 = **0.091**。对照几乎只在三条 goal 上做成；摆放和朝向对照全是 0。

## 任务从哪来

每个 `libero_object_swap` 场景只改一处：

| 轴 | 条数 | 实际改动 |
| --- | ---: | --- |
| goal | 10 | 改 `(:language)`、`(:obj_of_interest)`、`(:goal)`，换成场上已有的另一件物体。区域和源 init 不动，丢掉复位后已经成功的状态 |
| placement | 10 | 被操作物体所在 region 的 `(:ranges)` 沿 x 平移 −0.10 m，重采 50 条 init |
| geometry | 10 | 同一 region 加上 `yaw_rotation=π/2`，重采 50 条 init。不改网格、不改尺寸 |

goal 的替换是预先指定的一对一，不是场上物体的排列组合：

| 源要抓的 | 新指令改成抓 |
| --- | --- |
| alphabet soup | salad dressing |
| bbq sauce | chocolate pudding |
| butter | tomato sauce |
| chocolate pudding | ketchup |
| cream cheese | alphabet soup |
| ketchup | cream cheese |
| milk | butter |
| orange juice | chocolate pudding |
| salad dressing | tomato sauce |
| tomato sauce | milk |

编号按源文件名排序，每个源布局连续三条：`task01/04/07/…` 是 goal，`02/05/08/…` 是平移，`03/06/09/…` 是转 90°。

新 BDDL 和 init 写在 LIBERO-PRO 的 `pro_object_batch_20261004_task/` 下，没有写回 `libero_object_swap`。runner 的 `max_steps_for_suite` 把这个 suite 映射到 object 轴的 280 步。

## 这次 benchmark 记什么

同一 task、同一 seed、同一 init 下标，pack 和对照成对。没有「该用的 skill」。正例不是泛化标签。

第一层用对照当尺子，看 skill 触得对不对：对照做不成 = 需要接手。

| | 对照失败 | 对照成功 |
| --- | --- | --- |
| pack 触发 | 正确触发 | 误触 |
| pack 未触发 | 漏触 | 正确不触发 |

第二层只看进了 recovery 的集：触发后成功 / 触发后失败。`skill_id` 来自 `recovery_trace.jsonl` 里第一条 `kind=rule`。对照成功而 pack 失败记成干扰。不把「触发了」写成泛化成功。

## 总表

| | 集数 | 成功 | 成功率 | `recovery_calls>0` |
| --- | ---: | ---: | ---: | ---: |
| pack | 1500 | 1317 | 0.878 | 1338（0.892） |
| 对照 | 1500 | 136 | 0.091 | 0 |

按轴（各 500 集）：

| 轴 | pack | 对照 | pack 触发 |
| --- | ---: | ---: | ---: |
| goal | 439/500 = 0.878 | 136/500 = 0.272 | 350/500 |
| placement | 427/500 = 0.854 | 0/500 = 0 | 493/500 |
| geometry | 451/500 = 0.902 | 0/500 = 0 | 495/500 |

1500 对 episode 全部对齐。

| 触发判定 | 集数 |
| --- | ---: |
| 正确触发（对照失败且 pack 触发） | 1338 |
| 误触（对照成功且 pack 触发） | 0 |
| 漏触（对照失败且 pack 未触发） | 26 |
| 正确不触发（对照成功且 pack 未触发） | 136 |

触发精确率 1338/1338 = 1.000。触发召回率 1338/(1338+26) = 0.981。漏触 26 条里 goal 14、placement 7、geometry 5。

进门之后：1172/1338 = 0.876 做成，166 失败。误触是 0，这 1172 全是该触且触了之后做成的。另有 13 条对照失败、pack 没触发却做成（VLA 自己做成），算抬高但不算 skill 成功。抬高合计 1185。干扰 4 条：对照成功、pack 失败，且都没触发，不是 skill 帮倒忙。

按轴的触发后成功率：goal 294/350，placement 427/493，geometry 451/495。

## 逐任务

物体列是这条任务语言里要抓的东西。goal 行的源物体见上一节对照表。

| task | 轴 | 物体 | pack | 对照 | pack 触发 |
| ---: | --- | --- | ---: | ---: | ---: |
| 01 | goal | salad dressing | 49/50 | 44/50 | 0 |
| 02 | placement | alphabet soup | 50/50 | 0/50 | 50 |
| 03 | geometry | alphabet soup | 50/50 | 0/50 | 50 |
| 04 | goal | chocolate pudding | 50/50 | 0/50 | 50 |
| 05 | placement | bbq sauce | 50/50 | 0/50 | 50 |
| 06 | geometry | bbq sauce | 49/50 | 0/50 | 50 |
| 07 | goal | tomato sauce | 41/50 | 0/50 | 50 |
| 08 | placement | butter | 42/50 | 0/50 | 50 |
| 09 | geometry | butter | 38/50 | 0/50 | 50 |
| 10 | goal | ketchup | 50/50 | 49/50 | 0 |
| 11 | placement | chocolate pudding | 17/50 | 0/50 | 50 |
| 12 | geometry | chocolate pudding | 38/50 | 0/50 | 50 |
| 13 | goal | alphabet soup | 47/50 | 0/50 | 50 |
| 14 | placement | cream cheese | 28/50 | 0/50 | 44 |
| 15 | geometry | cream cheese | 31/50 | 0/50 | 45 |
| 16 | goal | cream cheese | 45/50 | 0/50 | 50 |
| 17 | placement | ketchup | 50/50 | 0/50 | 50 |
| 18 | geometry | ketchup | 49/50 | 0/50 | 50 |
| 19 | goal | butter | 13/50 | 0/50 | 50 |
| 20 | placement | milk | 48/50 | 0/50 | 50 |
| 21 | geometry | milk | 50/50 | 0/50 | 50 |
| 22 | goal | chocolate pudding | 48/50 | 0/50 | 50 |
| 23 | placement | orange juice | 49/50 | 0/50 | 49 |
| 24 | geometry | orange juice | 50/50 | 0/50 | 50 |
| 25 | goal | tomato sauce | 46/50 | 43/50 | 0 |
| 26 | placement | salad dressing | 49/50 | 0/50 | 50 |
| 27 | geometry | salad dressing | 50/50 | 0/50 | 50 |
| 28 | goal | milk | 50/50 | 0/50 | 50 |
| 29 | placement | tomato sauce | 44/50 | 0/50 | 50 |
| 30 | geometry | tomato sauce | 46/50 | 0/50 | 50 |

对照能做成的三条（01、10、25）都是 goal，pack 也几乎不触发。弱项仍是黄油和奶油奶酪：goal 把牛奶改成黄油只有 13/50；巧克力布丁平移 17/50；奶油奶酪平移 28/50、朝向 31/50。牛奶和橙汁的纸盒在平移/朝向上已经能做。

## 进门的 skill

`recovery_trace` 第一条 `kind=rule` 的 `skill_id`。次数是触发集数，不是成功标签。

| skill | 触发后成功 / 触发 |
| --- | ---: |
| `object_basket_persistent_wrong_intent_group_a` | 640/750 |
| `object_basket_bbq_orange_precontact_wrong_intent` | 198/199 |
| `object_basket_tomato_persistent_wrong_intent` | 102/116 |
| `object_basket_salad_dressing_precontact_wrong_intent` | 99/100 |
| `object_basket_cream_cheese_precontact_wrong_intent` | 96/130 |
| `object_basket_cream_tomato_q5_wrong_intent_window` | 37/43 |

六条合计 1338，和 pack 触发集数对得上。

## 日志位置

pack 前三条在 `.../pro_object_batch_20261004_mrs200/pack/pack/`。task03 在中途断过，从 episode 24 续跑，50 条齐。其余 pack 和全部对照在 `.../lanes/l{0-3}/`。driver 日志在各 lane 的 `driver.log`。

不要和 2026-09-30 的六套源 suite 评测混用。那次目录是 `logs/libero_pro_six_suite_pack36_20260930/`，测的是未改造的 swap/task/goal/spatial；object_swap 当天 0/500 是语言设置问题，第二天 `logs/libero_object_swap_bddl_20261001/` 用 bddl/bddl 重跑才是 438/500。
