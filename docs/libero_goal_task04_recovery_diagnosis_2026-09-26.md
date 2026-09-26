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
| ~~place 落点太深/太高~~ | 把 inner-floor 的 place 候选沿 y 从抽屉深处 `y=-0.0903` 推到开口外 `y=+0.03`（12 cm） | **这个实验无效，结论作废。** 见下方更正：真实 backend 从不读 `place_candidates`，那次扫的是一个死变量 |
| 抓取位姿的坐标系复合错了 | 逐步复算 `world_from_obj @ action_6dof_to_mat4x4(grasp) @ tool_from_ee` 并与 trace 对齐 | 位姿**正确**：刀尖落在 `(0.60133, 0.13438, -0.00442)`，离奶酪中心 `(0.60133, 0.13438, -0.00308)` 仅 **1.3 mm** |
| `Pick:end` 的 `IK_FAIL` 是 partial-pose metric 造成的 | 运行时 monkeypatch 清空 `pose_cost_metric` 重试 | 仍是 `IK_FAIL`（5/5）。metric 不是原因 |

### 更正：place 位姿不走 `place_candidates`

早先本文写过"place 目标是对的，不是 bug"，依据是 `place_candidates` 的面键条目
（`center_only` → 面中心 `(0.6918, -0.0903, 0.19862)` = `open_drawer_release_pos`）。**这个依据是错的。**

`grep -rn 'place_candidates'` 在整个 `third_party/cuTAMP/cutamp/` 下**零匹配**。真实 backend 里
Place 的位姿由 `particle_initialization.py:223-285` 现场采样：

```python
surface_curobo = world.get_object(surface)      # 面的碰撞几何，不是我们的候选表
sampled_placements = place_4dof_sampler(
    num_particles * 2, obj_curobo, obj_spheres, surface_curobo,
    surface_rep=self.config.placement_check,
    shrink_dist=self.config.placement_shrink_dist, ...)
```

`place_4dof_sampler`（`samplers.py:133-217`）按 `surface_rep`（`obb` / `aabb`）在**面的几何**上撒点，
再按 `obj_z_delta` 抬到面表面之上。`problem.place_candidates` 只被我们自己的 lite planner
（`cutamp_like_v2.py:106`）消费，真实 backend 完全不读。

所以：**要改 place 位姿的分布，要改的是面对象给 cuTAMP 的碰撞几何、`placement_check`、
`placement_shrink_dist` 和 yaw 采样，而不是 `place_candidates`。** 那条 12 cm 扫描改的是死变量，
它的"无关"结论无效——事实上病因完全在别处（见第 4 节）。


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

### 轨迹扫描：碰撞不只在起点

`collision_attribution_probe.py --result-json <...>.result.json --interpolate 6` 沿
`optimized_plan` 的 `q0/q1/...` 做关节空间插值，逐点报最深的障碍物。对记录基线那个
`holding(cream_cheese_1_main)` problem：

```
segment     waypoint   t      penetration  obstacle
MoveFree    q0         0.00     +0.01015   wooden_cabinet_1_cabinet_top__mj_geom_180
MoveFree    q0->q1     0.14     +0.02567   wooden_cabinet_1_cabinet_top__mj_geom_173
MoveFree    q0->q1     0.29     +0.02845   wooden_cabinet_1_cabinet_top__mj_geom_180   <- 最深
MoveFree    q0->q1     0.43     -0.01243   (已脱离)
Pick@q1     q1         0.00     +0.00068   akita_black_bowl_1_main__mj_geom_113
```

"轨迹后面还撞谁"的答案是**同一个柜顶**，但**中段比起点深 2.8 倍**（+2.85 cm vs +1.02 cm）。
只探 `q_init` 一个点会低估这个问题。

一个需要留意的读数差异：在最终**成功**的那个 holding solve 上跑同一个扫描，`q0` 处仍报
+0.01028 m。这不是探针错误——cuTAMP 自己的 `plan_start_collision_escape` 会临时
`enable_obstacle(False)` 掉这些 blocker（本 episode 的 motion trace 记录了一次
`start_collision_escape_success`），所以它能在探针认为碰撞的起点上规划。探针量的是
"机器人 vs 完整世界"，与 cuRobo 当时实际启用的障碍集合不同。

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
export CUTAMP_LOG_LEVEL=INFO    # cuTAMP 自己的 skeleton / plan 数 / 每步残差（落在 cutamp_debug/*.stderr.txt）
export CUTAMP_LOG_LEVEL=DEBUG   # 再加逐约束满足向量、Place 的 IK success 计数
export CUTAMP_RECOVERY_DIAG_JSONL=<run_dir>/recovery_diag.jsonl # recovery 的每次决策（含 start_state_retreat）

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

## 6. 放置失败的真因：Place 的手部位姿 IK 0/64

打开 cuTAMP 自己的日志级别（`CUTAMP_LOG_LEVEL`，见第 5 节备注）后，两件事一次看清。

**先看 skeleton**（`algorithm.py:477` 的 `_log.info`）：

```
place goal  : Num plans: 1, num skipped: 0
              [Opt 1] Optimizing plan ['MoveFree(q0, traj1, q1)',
                'Pick(cream_cheese_1_main, grasp1, q1)',
                'MoveHolding(cream_cheese_1_main, grasp1, q1, traj2, q2)',
                'Place(cream_cheese_1_main, grasp1, pose1,
                       wooden_cabinet_1_top_region_inner_floor, q2)']
holding goal: [Opt 1] Optimizing plan ['MoveFree(q0, traj1, q1)',
                'Pick(cream_cheese_1_main, grasp1, q1)']
```

于是"`pos_err` 属于 Place"从推断变成**观测**（Pick 两边都有，Place 只有前者有），
并且确认这个 goal 真的只有 **1 个** skeleton。另外注意 Place 的位姿参数是独立的 `pose1`。

**再看 IK**（`CUTAMP_LOG_LEVEL=DEBUG`，`particle_initialization.py:305` 的 `log_debug`）：

```
Place(cream_cheese_1_main, grasp1, pose1, wooden_cabinet_1_top_region_inner_floor, q2). IK success: 0/64
```

紧接着的代码是：

```python
ik_result = world.ik_solver.solve_batch(world_from_ee, seed_config=None)  # TODO: seeding?
log_debug(f"{header}. IK success: {ik_result.success.sum()}/{num_particles}, ...")
particles[q] = ik_result.solution[:, 0]        # 无条件写入，不检查 ik_result.success
```

**Place 的手部位姿 IK 对 64 个粒子全部失败，而失败解被无条件写进 `particles[q2]`。**
优化器就是从这 64 个无效初值出发的，所以 `pos_err`（= ‖FK_EE(q2) − 期望 EE‖）卡在
6–9 cm 降不下去。这解释了此前所有"不敏感"现象：Place 的 q2 初值只依赖 IK，跟 `q_init` 无关，
也跟我们改的 `place_candidates` 无关。作者在那行自己留了 `# TODO: seeding?`。

尚未区分两个子因，二者需要的修法完全不同：

1. **采样出的手部位姿本身不可达**（工作空间/姿态超出 panda 能力）→ 要改的是**面给 cuTAMP 的
   碰撞几何**、`placement_check`、`placement_shrink_dist`、yaw 范围，让采样落在可达集内；
2. **IK 没给种子所以不可靠**（`seed_config=None`）→ 要改的是给 `solve_batch` 传种子
   （例如 plan 里的 `q1` 或当前位形）。注意 `Pick` 的初始化分支是怎么做的，对比即可看出差别。

**`pos_err` 仍未修复。** 需要注意它**在成功那次 episode 里依然出现**：成功 run 的 6 个 solve 中，
3 个 place goal solve 全部是 `No satisfying particles found` + `pos_err 0/64`；3 个
`feasible=True` 的都是 holding goal。也就是说端到端成功**不是**靠 cuTAMP 把物体放进抽屉
达成的，而是靠"recovery 抓取成功 + VLA 完成放置"这条路径。

已排除的相关线索：起态碰撞、抓取位姿的坐标系复合、`Pick:end` 的 partial-pose metric、
以及抽屉铰接模型（该 problem 的 `articulations={}`、`articulation_options={}`，抽屉被建成静态的
`wooden_cabinet_1_top_region_inner_floor` 虚拟内底面——见第 0 节关于"语义被降级"的讨论）。

### 6.1 真因：4-DOF 放置的坐标系约定与物体实际躺姿差 90°

`place_4dof_sampler` 只采 `(x, y, z, yaw)`，调用方用 `action_4dof_to_mat4x4` 造物体位姿——
即"单位姿态 + 绕世界 z 的 yaw"。这隐含假定**物体局部 z 就是它躺平时的朝上轴**。

而从 MuJoCo box geom 注册进来的物体不满足这个假定：奶酪交给 cuTAMP 的是 geom 自己的坐标系
（`_cuboid_from_single_box_part`，`real_cutamp_backend.py:401`），`dims=[0.0179, 0.0427, 0.0812]`，
**薄的那条是局部 x**。于是：

* 采样器把物体"竖起来立在端面上"；抓取是在物体坐标系里定义的，手就跟着转 90°：
  实测放置的手 z 轴 = `(-0.956, -0.292, 0)`（横着），而 pick 的手 z 轴 = `(0, 0, -1)`（朝下）。
* `obj_z_delta`（读物体球拟合的**局部 z**）因此按"站着的高"算，得到约 5 cm 而不是约 1.7 cm。

离线复现：`IK on 128 reproduced PLACE hand poses: success=0/128`。放置的 x/y 是对的
（x∈[0.6005,0.7789]、y∈[−0.1557,−0.0253]，都在内底面范围内），**只有姿态差 90°**。

注意：`_cuboid_dims`/`_cuboid_pose` 只服务 surface 和 fallback proxy，**movable 走的是
`_cuboid_from_single_box_part`**；改前两者对奶酪毫无影响（这一点最初判断错过）。

### 6.2 按"物体真实躺姿"修正后的实测效果（部分成功）

`scripts/recovery/skill_pipeline/patch_cutamp_place_rest_frame.py`（env-gated
`CUTAMP_PLACE_REST_FRAME=1`，默认关闭）在 Place 分支把位姿改成 `Rz(yaw) @ R_rest`，
并用物体在**躺姿**下的球拟合重算落点高度：

| | IK success | rest_drop | 物体中心 z | feasible |
|---|---|---|---|---|
| 关闭 | **0/64** | —（局部 z 当竖直） | ≈ 0.20 | False |
| 打开 | **2/64** | 0.0170 | 0.1677 | False |

方向被证实（IK 0→2，高度误差从 ~5 cm 降到 1.7 cm），但**尚未修好**：2/64 说明
"yaw 在 [0, 2π) 上均匀采样"仍让绝大多数样本的手部位姿不可达——抽屉口只有约 6 cm 高，
只有很窄的一段 yaw 存在腕部解。同时 `rot_err <= 0.05` 现在才作为失败项出现（关闭时它不报失败），
说明姿态修正还没完全对上。下一步应把 yaw 从"均匀随机"改为"以物体当前 yaw 为基准的窄带"，
或按 IK 可行性直接挑选放置位姿。



