# object 轴直立纸盒：抓取 profile `carton_upright_body_side_v1`（含高度扫描与 seeds 1–50 决胜）

日期：2026-09-20
范围：milk / orange juice 的**直立纸盒抓取**（`libero_object_task` t05/t07、`libero_object_swap` t08/t10）。
本轮的背景是上一轮撤回的那条坏 hint（见 `docs/libero_object_axis_carton_hint_regression_2026-09-20.md`）：
撤回后纸盒回到通用 `libero_topdown` 采样器，四个 task 在 seeds 1–50 上是 **105/200**。

## 1. 问题定位：通用采样器对纸盒只有"一个高度"

`_topdown_samples()` 对纸盒给出 **40 个候选 = 5 个横向偏心 × 8 个 yaw × 1 个高度**，且那个高度是
`z = 半高 − 0.02`，在物体坐标系里等于 **离桌面 11.12 cm（85% 高度）**。而纸盒的真实几何（取自
`assets/stable_hope_objects/{milk,orange_juice}/*.xml`）是：

| 部位 | 范围（离桌面） | 尺寸 |
| --- | --- | --- |
| 盒身 | **0 – 10.95 cm** | 0.0525 × 0.0525 m 等截面方柱 |
| 尖顶 | 10.95 – 13.12 cm | 两块对倾斜板 |
| 顶棱条 | 13.12 cm | 宽 5.9 mm，横跨 5.3 cm |

也就是说通用采样器的 40 个候选**全部落在离盒身顶只剩 1.7 mm 的斜顶起点上**。实测（seeds 1–50，撤回包）：

- 成功的抓取：闭合开度中位 0.0269 m（≈ 盒身半宽）、物体被提起 0.021 m；
- 失败的抓取：开度 0.0033 m（几乎全闭 = 夹空）、物体纹丝不动（`object_lift_m ≈ 1e-4`）；
- **对角 yaw 抓 15 次失败 13 次**（对角跨距 ≈ 7.4 cm > 盒身 5.25 cm）。

结论：纸盒缺的不是"更好的参数"，而是**采样器的结构里没有"抓盒身"这个选项**。

## 2. 新 profile：`carton_upright_body_side_v1`

`skills/fail_only/recovery_hint/grasp/grasp_carton_upright_body_side.md` +
`code/grasp_profiles.py::_carton_body_side_samples`：

| 项 | 取值 |
| --- | --- |
| 采样位置 | 物体中心 (0, 0)，z = `CARTON_GRASP_HEIGHT_FRACTIONS` × 总高（离桌面） |
| 朝向 | **yaw = 0° 与 180°**：闭合轴沿物体 **x 轴 = 棱的方向**（supervisor 选定的 A 方案），两个手腕滚转给规划器留 IK 退路 |
| 目标开度 | 盒身宽 + 6 mm |
| 作用域 | `target_name_matches: milk\|orange_juice` + `target_orientation_is: upright` + `target_name_excludes: …` |

静态门（`scripts/recovery/skill_pipeline/check_grasp_skills.py`）：**0 error / 0 warning**，且仓库预置的 canary
`milk_upright` **精确命中**（期望 `grasp_carton_upright_body_side / carton_upright_body_side_v1`）。
注意仓库还为**倒下的纸盒**预留了另一条 canary（`grasp_carton_fallen_body_side`），本轮不做：我们的 episode 都是直立盒。

## 3. 高度扫描（dev seeds 51–65，4 个纸盒 task，每臂 60 集）

四个臂是四个独立包，唯一差异是代码里的高度元组（index md5 全部相同 `b32e5a1024daa74e3fc771a726d2eeb9`）：

| 臂 | 高度档 | task 轴 t05/t07 | swap 轴 t08/t10 | 合计 |
| --- | --- | ---: | ---: | ---: |
| h70 | 70%（9.18 cm） | 5/30 | 2/30 | **7/60** |
| h75 | 75%（9.84 cm） | 28/30 | 24/30 | **52/60** |
| **h80** | **80%（10.50 cm）** | **30/30** | **30/30** | **60/60** |
| hall | 70/75/80 三档 | 30/30 | — | 30/30 |
| 对照 | 通用采样器（无该 profile） | — | 12/30 | 18/40（含 task 轴 10 集） |

**h70 为什么反而最差**：25/25 失败集都出现 `real_cutamp_no_feasible_goal`（规划不可行），而不是抓不住——
少数执行到的抓取开度 0.0269、提起 0.021 m 完全正常。高度影响的是**规划可行性**（极可能是夹爪手掌体与盒顶棱、
邻物的碰撞约束），不是夹持质量。

扫描结论：**80%（离桌面 10.50 cm，离盒身顶 4.5 mm）** 是最优档位，已烘焙为常数
`CARTON_GRASP_HEIGHT_FRACTIONS = (0.80,)`。

## 4. seeds 1–50 决胜（4 个纸盒 task × 50 集 = 200 集）

| task | 物体 | 新 profile | 通用采样器（撤回包） |
| --- | --- | ---: | ---: |
| `libero_object_task` t05 | milk | 49/50 | 38/50 |
| `libero_object_task` t07 | orange juice | 49/50 | 24/50 |
| `libero_object_swap` t08 | milk | **50/50** | 23/50 |
| `libero_object_swap` t10 | orange juice | 49/50 | 20/50 |
| **合计** | | **197/200 = 0.985** | 105/200 = 0.525 |

机制指标（逐集汇总）：

| 指标 | 新 profile | 撤回包（通用采样器） |
| --- | ---: | ---: |
| 抬升探针 `object_followed` 为真的集数 | **200/200** | — |
| 闭合开度中位 | 0.0269–0.0270 m（≈ 盒身半宽 0.02625） | 失败集 0.0033 m |
| 物体被提起中位 | 0.021–0.023 m | 失败集 ≈ 0 |
| `place_lift_too_low` 次数 | **0** | — |
| `real_cutamp_no_feasible_goal` 次数 | **4** | 398 |

**3 集失败的模式**：全部是 `ep00 / seed=1`（t05、t07、t10 各一集，t08 的 ep00 成功），每集 2 次 recovery 调用、
其中 1 次 `no_feasible`。即：该初始摆放下"0.80 单档给的两个候选"不够用。待验证的后续假设：
**给第二档（0.75 + 0.80）** 能否补上这 3 集（`arm_h7580`，只跑 4 个 ep00 的定向小实验）。

## 5. 运行环境说明（本轮 3 次抢占）

平台在本轮内 **3 次抢占**该 pod（12:14 内存重调度、12:32 `debug-kimi-true-copy`、13:36 `wt-gpu-sra2`）。
因此新增了**可断点续跑的驱动**（`F:\dsh_test\inspire-driver\relaunch_carton_final.sh`：逐 task 数已完成集数，
用 `--episode_index_start` 续跑，已完成/在跑的自动跳过）与**自动续跑循环**（`auto_resume_final.py`：
每 7 分钟探测一次，断了自动补）。决胜验证就是在被抢占两次后由它自动续完的。

## 6. 产物与校验

| 项 | 值 |
| --- | --- |
| 工作包 `skills/_index.yaml` | **`b32e5a1024daa74e3fc771a726d2eeb9`**（32 条） |
| `code/grasp_profiles.py` | md5 `e6ae8ac193419c2c9a35381ff09a4021` |
| 新 hint | `skills/fail_only/recovery_hint/grasp/grasp_carton_upright_body_side.md`（md5 `05f476d151f89e246bb62ed40bc169c4`） |
| `capabilities.yaml` | `grasp_profiles` 增加 `carton_upright_body_side_v1` |
| 决胜产物归档 | `remote_outputs/carton_final_20260920/`（tarball md5 `25512699fb17748fea84b099b2c28058`） |
| 扫描包与日志 | 实例 `$WORK/logs/carton_profile_20260920/{base,arm_h70,arm_h75,arm_h80,arm_hall}` |
| 分析脚本 | `openvla-oft/experiments/{check_carton_profile.py,carton_draw_*.py,summarize_carton_final.py}` |

## 7. 下一步

1. **定向小实验**：`arm_h7580`（0.75 + 0.80）在 4 个 `ep00/seed=1` 上跑，看能否把 197/200 补到 200/200（pod 抢占后待重跑）。
2. **butter / flat box**：flat-box profile 同样是"固定深抓点、没有高度维度"，计划照抄本轮方法做高度扫描
   （butter 在 seeds 1–50 上是 58/100，失败模式是"闭合后丢双边接触"）。
3. **cream cheese**：瓶颈在触发覆盖（task 轴 26/50），codex 的 R2 触发候选在 seeds 1–50 上主轴无增益
   （B0 25/50 vs B1 22/50，swap 轴 36→41），未采纳；剩余缺口需要新增"连续任意非目标意图"谓词（代码级改动）。
