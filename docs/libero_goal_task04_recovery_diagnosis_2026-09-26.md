# LIBERO-Goal task04 recovery 诊断：起态碰撞与抓取位姿两层墙

本文记录 2026-09-26 对 LIBERO-Goal task04（`open_the_top_drawer_and_put_the_bowl_inside`，
语言 "Open the top layer of the drawer and put the cream cheese inside"）强制 recovery
失败原因的排查。结论是**两层独立的墙**，都已定位并各自有对应修复。

复现的 episode 身份：`task_id_1based=4, episode_seed_start=51, seed=90,
force_recovery_query=12, max_recovery_calls=2, num_env_steps=300, recovery_calls=1,
success=False`。

## 0. 先确认病灶不在哪

排查过程中有三个假设被实验证伪，记下来避免重复走：

| 假设 | 实验 | 结果 |
|---|---|---|
| 起态碰撞是 recovery 失败的根因 | `q_init` 换成退让后的自由解、以及 `q_init=None`（完全去掉起点约束）各解一次 | `pos_err 0/64` **三者完全一致**。控制组有效：`no_q_init` 的 `q_init_present=false`、`robot_alignment_debug.q_init=null` |
| place 落点太深/太高 | 把 inner-floor 的 place 候选沿 y 从抽屉深处 `y=-0.0903` 推到开口外 `y=+0.03`（12 cm） | `pos_err 0/64` 全程不动，min 残差恒为 0.06–0.09 m |
| 抓取位姿的坐标系复合错了 | 逐步复算 `world_from_obj @ action_6dof_to_mat4x4(grasp) @ tool_from_ee` 并与 trace 对齐 | 位姿**正确**：刀尖落在 `(0.60133, 0.13438, -0.00442)`，离奶酪中心 `(0.60133, 0.13438, -0.00308)` 仅 **1.3 mm** |
| `Pick:end` 的 `IK_FAIL` 是 partial-pose metric 造成的 | 运行时 monkeypatch 清空 `pose_cost_metric` 重试 | 仍是 `IK_FAIL`（5/5）。metric 不是原因 |

关于 place 候选点的一个易误读现象：`place_candidates` 里 key 为**物体名**的条目（如
`cream_cheese_1_main: [(0.6013, 0.1344, 0.1569), ...]`）其 xy 就是物体自身位置，是
`tamp_scene.py:1916-1917` 给场景里每个物体生成的通用"放到桌上"启发式。算子
`place_on(cream_cheese_1_main, wooden_cabinet_1_top_region_inner_floor)` 的
`continuous_parameters` 是 `place_candidate(wooden_cabinet_1_top_region_inner_floor)`，
绑的是**面键**，走 `tamp_scene.py:1918-1930` 的 `_inner_floor_place_candidates` →
`center_only` → 面中心 `(0.6918, -0.0903, 0.19862)`，等于 `open_drawer_release_pos`。
**place 目标是对的，不是 bug。**

## 1. 两个 goal 死在不同的地方

该 episode 只序列化了两个 cuTAMP problem：

| problem | goal | 失败位置 |
|---|---|---|
| `solve_1790431743267_399455` | `on(cream_cheese_1_main, wooden_cabinet_1_top_region_inner_floor)` + `handempty()` | `[KinematicConstraint] pos_err <= 0.005 has 0/64 satisfying` |
| `solve_1790431801800_399455` | `holding(cream_cheese_1_main)` | 粒子层通过（5–7 个满足），死在 MotionGen |

两者只差一个 `Place` 算子，而第二个 problem 的约束输出里**没有 `pos_err` 那一行**。
所以 `pos_err 0/64` 属于 **Place 算子**，与抓取无关；而起态碰撞的影响只体现在第二个
problem 的 MotionGen 上（第一个 problem 根本走不到 MotionGen）。

## 2. 第 1 层：起态与世界碰撞

打开 cuTAMP 自带的 trace（`CUTAMP_MOTION_TRACE_JSONL=<path>`，实现在
`third_party/cuTAMP/cutamp/motion_solver.py` 的 `_trace_motion_event`）后，逐 stage 的
cuRobo 状态直接可见：

| 起态 | 失败 stage | 状态 |
|---|---|---|
| 碰撞的 `q_init` | `Pick:pick_approach` | `MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION` |
| 退让后 | `Pick:end` | `MotionGenStatus.IK_FAIL` |
| 完全去掉 `q_init` | `Pick:end` | `MotionGenStatus.IK_FAIL` |

trace 里 baseline 的 `start_q` 正是那个碰撞的 `q_init`
`[0.0397, 0.5554, 0.0671, -1.6627, -0.0698, 2.2661, 0.8277]`。cuRobo 对"起点已穿入世界"
是**直接拒绝**，而 recovery 的 64 个粒子共享同一个起点，所以在任何搜索发生之前就失败了——
再怎么优化粒子都修不好。

碰撞本身：该 `q_init` 下夹爪球 57 撞 `wooden_cabinet_1_cabinet_top__mj_geom_180` **+0.01015 m**；
一次退让迭代后为 **-0.00574 m**（自由）。

**修复**：`--start_state_retreat`（commit `66c70e7`）。在这个 flag 下，plan 不可行时先让
py3.10 子进程在它自己的碰撞世界里搜退让位形，再用 LIBERO 路点桥把手臂走过去，重新感知并重规划。
默认关闭。

## 3. 第 2 层：采样抓取位姿落在 IK 可达边界之外

清掉 metric 后，在**真实抓取位姿**上做 yaw × 深度网格（每格都问 cuRobo 同一个 IK 问题）：

| yaw | dz=0 | +0.005 | +0.010 | +0.020 | +0.030 |
|---|---|---|---|---|---|
| 0° | **IK_FAIL** | **IK_FAIL** | OK | OK | OK |
| 180° | **IK_FAIL** | **IK_FAIL** | OK | OK | OK |
| 90° | OK | OK | OK | OK | OK |
| 270° | OK | OK | OK | OK | OK |

即：采样器发出的那个位姿可达性差约 1 cm，而**附近存在可达解**。作为存在性证明，让探针接受
其中一个位姿后该 problem 返回 `feasible=True`、`num_satisfying=7`、`executable_plan` 4 步
——这是 P2 首次可行。

注意：平行夹爪只有 yaw 180° 是抓取等价的（绕接近轴对称）；yaw 90/270° 会改变爪子夹住物体的
哪条轴，对本物体（厚度 17.9 mm、宽 42.7 mm、长 81.2 mm，夹爪最大开度 80 mm）在物理上不成立。
所以**保抓取的修复只能走"浅一点"这条路**。

`Pick:end` 原本有一条 fallback，但它判断的是 `INVALID_PARTIAL_POSE_COST_METRIC`，
**不认 `IK_FAIL`**，所以这个失败没有任何退路。

**修复**：`scripts/recovery/skill_pipeline/patch_cutamp_end_pose_repair.py`。它给
`motion_solver.py` 的 `solve_curobo` 加一个 end-pose 修复循环，顺序是"最便宜且最等价优先"：
先试绕接近轴 180°（同深度），再试同姿态逐步变浅（`CUTAMP_END_REPAIR_DEPTHS_M`，默认
`0.005,0.010`）；yaw 90/270 因为不等价，藏在 `CUTAMP_END_REPAIR_ALLOW_NON_EQUIVALENT_YAW=1`
之后。补丁幂等、写前备份、支持 `--revert`。

在 P2 上验证通过：

```
pick_approach        True   None
end                  False  IK_FAIL
end_yaw180_dz+0.000  False  IK_FAIL        <- 等价 yaw、同深度，不够
end_yaw0_dz+0.005    True   None           <- 接受：同姿态、浅 5 mm
final_retract        True   None
```

接受的修复只比采样浅 5 mm；物体 z 向厚度 17.9 mm，刀尖仍在物体内部，爪子照样夹住物体。

## 4. 端到端结果与归因

每个 episode 约 3 分钟，所以补了两个对照把归因钉死。两次修复都是**必要且互不替代**的：

| run | 退让 | 补丁 | success | queries | env_steps | 接受的 end 修复 |
|---|---|---|---|---|---|---|
| 记录基线 | off | off | **False** | 61 | 300（撞上限） | — |
| **修复** | **on** | **on** | **True** | **37** | **177** | 3 |
| A | off | on | **False** | 61 | 300 | 1 |
| B | on | off | **False** | 61 | 300 | 0 |

逐 solve 的 `feasible` 字段（`cutamp_debug/*.result.json`）比 episode 结果更能说明机制：

| run | solves | feasible | 说明 |
|---|---|---|---|
| 记录基线 | 2 | **0** | place goal `pos_err 0/64`；holding goal MotionGen 5/5 失败 |
| **修复** | 6 | **3** | 3 个 holding solve 返回 `feasible=True`，`executable_plan` 4–5 步 |
| A | 4 | **2** | holding 可行（其中一个 `num_satisfying=32`），但 episode 仍失败 |
| B | 4 | **0** | holding 也失败：`Motion planning failed for 3/3`、`4/4` |

读法：

* **补丁（第 2 层）确实修好了抓取**：fix 与 A 里 `holding(cream_cheese_1_main)` 都返回
  `feasible=True` 并给出可执行轨迹；B（无补丁）全部死在 MotionGen。
* **退让（第 1 层）是 episode 成功的关键**：A 已经能规划抓取，但起态碰撞让 recovery 更早放弃
  （只有 4 个 solve、含 1 次 `INVALID_START_STATE_WORLD_COLLISION`），episode 仍失败。
* 端到端的成功路径是：**recovery 现在能抓取并执行，placement 由 VLA 接手完成**，于是
  300 步撞上限失败变成 177 步成功。

## 5. 复现路径

```bash
# 0. 环境
export ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
export CUTAMP_RUNNER_PYTHON=$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
export CUTAMP_MOTION_TRACE_JSONL=<run_dir>/motion_trace.jsonl   # 打开逐 stage trace

# 1. 打第 2 层的补丁（幂等，可 --revert）
python scripts/recovery/skill_pipeline/patch_cutamp_end_pose_repair.py

# 2. 用 runner.py 的 flag 打开第 1 层；skill_pack 必须用 --skill_index，
#    因为 cross_suite 那批 pack.yaml 里有 3/16 不是合法 YAML
python scripts/recovery/skill_pipeline/run_skill_eval.py \
  --task_suite_name libero_goal_task --task_ids 4 --num_trials_per_task 1 \
  --episode_seed_start 51 --seed 90 --force_recovery_query 12 --max_recovery_calls 2 \
  --skill_index <pack>/skills/_index.yaml \
  --start_state_retreat \
  --real_cutamp_grasp_dof 6 \
  --grasp_sampler_profile cream_cheese_flat_box_topdown_deep_v1 \
  --grasp_profile_adapter <pack>/code/grasp_profiles.py \
  --use_real_cutamp_backend --real_cutamp_require_feasible \
  --real_cutamp_curobo_plan --real_cutamp_serialize_trajectories \
  --prefer_real_cutamp_executable_plan --require_real_cutamp_executable_plan
```

注意 pack 自己的采样 profile 叫 `cream_cheese_flat_box_topdown_deep_v1`——pack **主动要求
"深"顶抓**，正好落在 IK 边界上，这是第 2 层之所以会触发的原因。

## 6. 仍然未解的问题

**`pos_err 0/64`（Place 算子）尚未修复。** 需要注意它**在成功那次 episode 里依然出现**：
成功 run 的 6 个 solve 中，3 个 place goal solve 全部是
`No satisfying particles found` + `[KinematicConstraint] pos_err <= 0.005 has 0/64 satisfying`；
3 个 `feasible=True` 的都是 holding goal。也就是说端到端成功**不是**靠 cuTAMP 把物体放进抽屉
达成的，而是靠"recovery 抓取成功 + VLA 完成放置"这条路径。

它不随起点、也不随 release 点变化，且与 `plan_type=NoneType`、`plan_summary=[]`、
`optimized_plan_present=false` 同时出现。

已排除的相关线索：起态碰撞、release 深度/位置、抽屉铰接模型（该 problem 的
`articulations={}`、`articulation_options={}`，抽屉被建成静态的
`wooden_cabinet_1_top_region_inner_floor` 虚拟内底面）。

