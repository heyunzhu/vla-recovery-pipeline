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

（6.2 那个调用点补丁已被 6.1 的源头修法取代，见 6.4；两者不要同时开。）

### 6.3 源头修法：给 cuTAMP 一个"立正"的物体坐标系

物化放置位姿的**不止一处**——`particle_initialization.py:278`（IK 种子）、
`motion_solver.py:526`（MotionGen）、以及 rollout（`pos_err` 的靶子）各自从粒子里重建它。
所以 6.2 那种只改一处的补丁**结构上不可能成立**，这也解释了它为什么只到 2/64。

正确做法是修**唯一源头**：`_cuboid_from_single_box_part`（`real_cutamp_backend.py:401`）。
用"把当前躺姿变成纯 yaw"的带符号置换（24 个右手置换里使 `(R·P)[2,2]` 最大的那个）
重新标定局部坐标系，并同步置换 `dims`。**物理上什么都没动**——描述的还是同一个盒子的
同样八个角（有测试断言），因此碰撞、grasp 采样、放置采样、rollout 靶子、MotionGen
自动保持一致。env-gated：`CUTAMP_CANONICAL_OBJECT_FRAME=1`。

实测（退让清过的起点，任务04 place problem）：

| 约束（最好值） | OFF | ON |
|---|---|---|
| `pos_err <= 0.005` | 34/64 | **63/64** |
| `rot_err <= 0.05` | 42/64 | **63/64** |
| `robot_to_world` | 25/64 | **24/64** ← 现在唯一瓶颈 |
| `robot_to_movables` | 62/64 | 64/64 |
| `movable_to_world` | 64/64 | 64/64 |

**运动学那堵墙拆掉了**，剩下的瓶颈换成了碰撞。

### 6.4 第 4 层：直线关节插值穿过柜顶，而 plan 里没有中间路点

`scripts/recovery/skill_pipeline/place_trajectory_probe.py` 在 `q_init` 与"放置位姿的
IK 解"之间做关节空间插值并逐点扫描（打开 canonical frame）：

```
phase     samples   worst penetration   obstacle
start       3       -0.00574 m          wooden_cabinet_1_cabinet_top__mj_geom_173
transit    33       +0.01535 m          wooden_cabinet_1_cabinet_top__mj_geom_173
goal        3       -0.00077 m          wooden_cabinet_1_main__mj_geom_171
```

**起点干净、目标干净、中间穿过柜顶 +1.5 cm。** 障碍物始终是柜顶那一组 geom
（171/173/174/177/180），不是更早猜的灶台或酒架。

原因不是"运动规划没绕开"，而是**根本没有中间路点可绕**。skeleton 是
`MoveFree(q0, traj1, q1)` / `MoveHolding(cream_cheese_1_main, grasp1, q1, traj2, q2)`，
而 `traj` 参数是 `null`；cuTAMP 自己也写着：

```python
q_start, traj, q_end = ground_op.values
if traj in best_particle:
    raise NotImplementedError("Trajectories not supported yet")
```

rollout 只能在端点配置之间做直线插值，碰撞代价就评在这条直线上。所以粒子要么让这条直线
恰好避开柜顶，要么就违约束——**这也正是 `robot_to_world 24/64` 的来源**：约三分之一的
采样放置确实存在干净的直线（某次扫描里 target 37 的最差值为 `0.00000`，恰好擦过），
但它们与"满足 `pos_err`/`rot_err` 的那 63/64"不重合，因为端点自由度不够同时兼顾两边。

可修的两个方向：

1. **采样器偏好/校验"直线可达"的放置**——现在的 `place_4dof_sampler` 只看落点是否在面上、
   z 方向是否压到物体，完全不看从起点过去的直线是否会扫到柜体；
2. **支持中间路点**（`traj1`/`traj2`），让优化器能绕过柜体——属于 vendored 改动，
   `NotImplementedError` 就在 `motion_solver.py` 的 `MoveFree` 分支。

实测产物：`$SSD/place_traj_on.json`、`$SSD/place_traj_off.json`（含每个采样点的最差障碍物与排名）。

## 7. 抓取用的是 pack 里现成的 profile，不是 cuTAMP 自己的采样器

第 5 节复现命令里的 `--grasp_sampler_profile cream_cheese_flat_box_topdown_deep_v1`
不只是个标签。所有 task04 运行都带 `--real_cutamp_grasp_dof 6`，于是
`real_cutamp_backend.py:2466` 会装上 `_allow_mesh_6dof_grasp_sampling(profile,
adapter_path=...)`，在整段 `run_cutamp` 期间把 `cutamp.samplers.grasp_6dof_sampler`
**和** `cutamp.particle_initialization.grasp_6dof_sampler` 一起换成
`_topdown_6dof`，后者调用 pack adapter 的
`skill_packs/libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914/code/grasp_profiles.py
::_flat_box_samples`。

第 5 节末尾早就写对了这一点（备注"pack 主动要求深顶抓"），但后续如果去读
`$WORK/third_party/cuTAMP/cutamp/samplers.py` 里的原生 `grasp_6dof_sampler`，读到的是
**运行时已被替换掉的死代码**：它 `pitch=0` 固定、`roll ∈ {±π/4,±π/3,±π/2}`（没有 0，
最小 45°）、`yaw ∈ {±π/2}`（没有 0）、完全忽略 `num_faces`，docstring 自己写着是给
bookshelf 域写的、不够通用。由此得出"cuTAMP 根本采不出顶抓"是**错的**。

`compare_grasps.py` 也踩了同一个坑：它 `from cutamp.samplers import grasp_6dof_sampler`
直接量，从来没有进入 `_allow_mesh_6dof_grasp_sampling`，所以它量的是原生采样器。

`$SSD/compare_grasps_profiled.py`（同一个 problem、同一个 object、同一进程内先量原生再量
装好 profile 的采样器）把两者分开：

```
                       canonical ON                canonical OFF
native  64 个互异       tilted 45 / sideways 19     sideways 64
        tool z mean     -0.429                      +0.000
        top_down        0                           0
profile 24 个互异       top_down 64                 top_down 64
        tool z mean     -1.000                      -1.000
        ee origin z     0.0988 .. 0.1006 m           0.0988 .. 0.1006 m
        sampler swapped by the profile: True
```

也就是说：**实际跑的那 64 个粒子全部是 tool 轴精确朝下的顶抓**，而且 canonical 开不开
都不影响（profile 用物体位姿算竖直轴，本来就跟着物体走）。compare_grasps.py 之前的
"OFF 64/64 sideways、ON 45 tilted + 19 sideways" 数字可以复现，它只是量的对象不对。

profile 给出的恰好是 24 个互异候选（`_topdown_6dof` 把 24 个循环填满 64 个粒子）：
2 个深度（物体顶面下 10.28 / 12.06 mm，即 TCP 落在中面下 1.3 / 3.1 mm）× 长轴 3 个偏移
（0 / ±3.25 mm）× 4 个 yaw（绕竖直轴 0 / ±90° / 180°）。奶酪 canonical 尺寸
`[42.67, 81.22, 17.87] mm`，`profile_gripper_width` 给 48.0 mm——注意这个 width 只进了
`tamp_scene.py:610` 的 `GraspCandidate.width`，而 `GraspCandidate` 在 real 后端只被
序列化进 problem JSON（`real_cutamp_backend.py:1333`）和记一个计数（:2540），
**从不注入 cuTAMP**（全仓 `grasps_obj` / `m2t2_grasps` 零命中），所以它不控制 6-DOF 路径
的夹爪开合。但 4 个 yaw 里有一半让手指跨 81 mm 长轴、另一半跨 42.7 mm 短轴，这一半是否
只是白占粒子数、还是要靠 cuTAMP 自己判碰撞淘汰，是需要逐候选实测的问题。

另外一个来源上的事实：这份 profile 是 pack 为 **task10（把 cream cheese 放到 rack 上）**
写的，配套 hint `skills/fail_only/recovery_hint/grasp/grasp_cream_cheese_flat_box_topdown_deep.md`
的 `applies_to` 明确要求 `goal_name_matches: wine_rack|rack`，而
`skills/_index.yaml` 是 `online: []`——hint 文档本身从不加载。task04 之所以用上它，纯粹是
我们的启动脚本把 profile 名字写死在命令行上。用现成 skill 没问题，但要记住它是从另一个
任务的挖掘产物里借来的，没有针对抽屉场景验证过。

## 8. 抓取真正的墙：那 24 个候选里，**没有一个**同时"不撞物体"且"IK 可解"

上节说"逐候选实测"，实测结果是确定性的、而且比预想的更糟。

先补一条 cuTAMP 自己的机制（`$WORK/third_party/cuTAMP/cutamp/particle_initialization.py`
的 Pick 分支）——采样器输出**不是**直接进 IK：

```python
num_samples = num_particles * 2                                  # 先 2 倍过采样
sampled_grasps = grasp_6dof_sampler(num_samples, obj_curobo, num_faces=num_faces)
grasp_spheres = transform_spheres(world.robot_container.gripper_spheres, obj_from_grasp)
grasp_coll    = sphere_to_sphere_overlap(obj_spheres, grasp_spheres, activation_distance=0.0)
collision_free_mask = grasp_coll <= 1e-2                         # 注意：1 cm 就算"不撞"
if collision_free_mask.any():
    selected_grasps = sampled_grasps[collision_free_mask][:num_particles]   # 按采样器顺序取前 N
else:
    selected_grasps = sampled_grasps[grasp_coll.topk(num_particles, largest=False).indices]
if selected_grasps.shape[0] < num_particles:                     # 不够就用 randint 有放回补
    selected_grasps = selected_grasps[torch.randint(0, selected_grasps.shape[0], (num_particles,))]
```

`$SSD/grasp_ik_on.json`（`scripts/recovery/skill_pipeline/verify_grasp_ik.py`，
problem = `open_drawer_run_20260926/cutamp_debug/solve_1790431801800_399455.problem.json`）：

```
particles : sampler called with 128 (2x oversample)  distinct=24  profile candidates=24
gripper-vs-object filter
  oversampled rows free : 64/128
  distinct candidates   : 12/24 free
  selection branch      : collision-free prefix of 64 rows
  selected rows         : 64  distinct=12
  candidate ranks in the selected set: #0x6 #1x6 #4x6 #5x6 #8x6 #9x6 #12x5 #13x5 #16x5 #17x5 #20x5 #21x5
real-scene IK success: 12/24        empty-world IK success: 12/24

 #   yaw   depth  xax yax  stradX stradY   gcoll free  real empty
 0    0.0  12.06    1   0    42.7   81.2    0.00  yes  FAIL  FAIL
 2   90.0  12.06    0   1    81.2   42.7   28.20   no    ok    ok
 3  -90.0  12.06    0   1    81.2   42.7   28.20   no    ok    ok
...
 1 -180.0  12.06    1   0    42.7   81.2    0.00  yes  FAIL  FAIL
(单位 mm；gcoll = 夹爪球与物体球的重叠深度)
```

两半分得干干净净：

| yaw | 夹爪状态 | gcoll | 真实场景 IK | 空世界 IK | cuTAMP 是否保留 |
|---|---|---|---|---|---|
| 0 / −180（12 个） | 手指干净 | 0.00 mm | **FAIL** | **FAIL** | **保留** |
| ±90（12 个） | 手指插进奶酪 | 25.6–32.7 mm | ok | ok | 丢弃 |

也就是说，cuTAMP 的前置碰撞过滤**恰好留下了 IK 解不了的那 12 个，丢掉了 IK 能解的 12 个**。
进优化器的 64 个粒子全部来自那 12 个不可解候选（ranks #0,1,4,5,8,9,12,13,16,17,20,21），
所以 `Pick(...). IK success: 0/64` 是**确定性**的，不是运气。另有两个关键否定：

* **和场景无关**：空世界 IK 与真实场景 IK 一样是 12/24，第 5 节"场景失败但空世界成功"是空的；
  而且 `ik world` 的 134 个障碍里**根本不含目标物体**（`includes target object: False`）。
  所以抓取失败不是柜子、不是桌面、也不是放置位姿。
* **和 canonical frame 无关**：`CUTAMP_CANONICAL_OBJECT_FRAME` 开/关都是 12/24，分组完全一致。

机制上讲得通：`grasp x closes` 时 yaw=0/−180 让手指跨 42.67 mm 短轴（干净），yaw=±90 让它跨
81.22 mm 长轴——夹爪开不到 81 mm，手指就扎进材料里（穿透 28–33 mm，比奶酪 17.87 mm 的厚度
还大）。而唯一干净的那两个朝向，在这个物体位姿下手腕不可达。

那到底是"profile 的 yaw 选得不好"还是"整个顶抓族在这个位姿下都堵死"？
`$SSD/grasp_sweep_on.json`（`scripts/recovery/skill_pipeline/probe_grasp_validity_sweep.py`，
16 个 yaw 偏移 × 2 个深度 = 32 个组合，同样的两项检查）：

```
verdict (CANONICAL ON)                CANONICAL OFF
  collision-free : 16/32                14/32
  IK-solvable    : 28/32 (empty 28/32)  28/32 (empty 28/32)
  BOTH           : 12/32                10/32
  usable yaw offsets from the long axis: {30, 45, 150, 210, 225, 330}
  => the profile's fixed yaw set {0,90,180,270} misses all of them
```

**答案：profile 的 yaw 集合就是病根。** 它只给 {0, 90, 180, 270}° 四个朝向：

* 0 / 180（贴着长轴）→ 干净但 IK **FAIL**（两个深度都 FAIL，共 4/32）；
* 90 / 270（横跨物体）→ IK ok 但手指扎进奶酪 31–47 mm，被过滤掉；
* 把 yaw 只挪 ±30°（即 30 / 150 / 210 / 330）→ **gcoll 仍是 0.00 mm，IK 就 ok 了**。

换句话说：偏 30° 就能同时满足两项检查，而这一族里恰好有 6 个这样的朝向，profile 一个都没给。
再加上过滤规则是"按采样器顺序取前 N"，被 24→128 循环填充后，**低 rank 的候选系统性占优**，
有效多样性实际上只有 12 个（甚至 2 个朝向 × 若干位置），这解释了为什么 `Pick:end` 的修复补丁
和 retreat 都只是在治症状。

可修的方向（未做）：

1. 给 pack 的 flat-box profile 加 yaw 偏移（±30°/±45°），或另起一个 profile id
   （pack 有 `SEAL.json`，加新 id 比改旧的干净）；
2. 注意 `grasp_coll <= 1e-2` 这个 1 cm 的"不撞"阈值本身很松——45°/225° 那两组 gcoll
   8.6/8.8 mm 也被判为 free，真正干净的只有 0.00 的那几个；
3. `_topdown_6dof` 的 24→N 循环填充 + cuTAMP 的"取前 N"叠加，使候选顺序直接影响谁被保留，
   值得改成按 rank 分散或先过滤再去重。

## 9. 临时修好的 profile：抓取那层的墙确实拆了

pack 是封存的，所以改法放在 pack 外面：`$SSD/tmp_grasp_profiles_yawfix.py`
（本地源 `experiments\.inspire\tmp_grasp_profiles_yawfix.py`），与封存 profile 逐行一致，
**只把 yaw 换成 `long_yaw + {+30, −30, +150, +210}°`**。它声明两个 id：

* `cream_cheese_flat_box_topdown_deep_yawfix_v0`，给独立探针用；
* **封存的那个 id 也声明**，即 shadow。原因：`capabilities.yaml` 是 `mode: strict`，
  而 `skill_pipeline/runtime.py` 对未注册的 `grasp_profile` 直接抛 `SkillSchemaError`，
  所以命令行只能传注册过的名字；shadow 同时保证 recovery hint 万一指名旧 id 也不会把旧实现
  拉回来。pack 目录一个字节没动。

先验（同一个 problem，`grasp_ik_yawfix.json`）：

```
gripper-vs-object filter
  oversampled rows free : 128/128
  distinct candidates   : 24/24 free
  selected rows         : 64  distinct=24
real-scene IK success: 24/24        empty-world IK success: 24/24
gcoll 全 0.00 mm，24/24 既 free 又 ik ok
```

再跑 `open_drawer_run_yawfix_20260927`（3 个 seed，其余 flag 与 `run_seeds3.sh` 完全一致）：

```
=== 决定性的那行 ===
  Pick 64/64  x4
  Pick 32/64  x3
  Place 36/64 x1
  Pick(...) 0/N occurrences: 0          <-- 封存 profile 下是 100% 的 0/64

=== solves ===
  goals=['on(cheese, wooden_cabinet_1_top_region_inner_floor)','handempty()']  feasible=True  sat=15
  goals=['inside(cheese, wooden_cabinet_1_top_region)','handempty()']          feasible=False sat=0   x6
  goals=['holding(cheese)']                                                    feasible=True  sat=42/49/38/9/28/23  x6

=== episodes ===
  ep00 seed51 success=True  13 queries 61 steps
  ep01 seed52 success=False 61 queries 300 steps   held=['cream_cheese_1_main'] 奶酪移动 0.087 m
  ep02 seed53 success=False 61 queries 300 steps   held=['akita_black_bowl_1_main']
```

结论分两半：

**抓取层确实修好了。** `Pick(...) IK success` 从"每一次都是 0/64"变成 64/64 与 32/64，
`0/N` 出现次数为 0；`holding` 目标 6/6 feasible（残留粒子 42/49/38/9/28/23）；
recovery #3 真的合上夹爪抓住奶酪并把 holding latch 置上（`lift_probe`，`all_goal_atoms_satisfied`）。
32/64 而不是 64/64 说明换一个物体位姿时四个偏移里有两个不可达，仍然 >0，符合预期。

**但 episode 成功率没变（1/3 → 1/3），因为剩下的墙不在抓取。** 见下节。
另外 ep00 的 `success=True` **不能算作放置能力的证据**：这次 recovery 的算子序列是
`['Pick','Pick','Pick']`，**一个 Place 都没有**，而且这一轮没有存 frames（`frames=0`，
`video: ""`），所以既没有放置动作也没有录像。封存 profile 那次 ep00 也是同样的形态。

## 10. `inside` 目标不可解的真正原因：一个名字解析 ValueError，不是几何

六次 `inside(cream_cheese_1_main, wooden_cabinet_1_top_region)` 全部 `feasible=False`，
`failure_reason` 完全一样，而且根本不是求解失败：

```
ValueError: Goal atom On(cream_cheese_1_main, wooden_cabinet_1_top_region) references unknown
surface literal 'wooden_cabinet_1_top_region' that does not appear in the initial state.
Known surface literals: ['flat_stove_1_burner', 'flat_stove_1_burner_plate', 'flat_stove_1_button',
'flat_stove_1_main', 'plate_1_main', 'table', 'wooden_cabinet_1_cabinet_bottom',
'wooden_cabinet_1_cabinet_middle', 'wooden_cabinet_1_cabinet_top', 'wooden_cabinet_1_main']
```

来源在 `experiments/robot/libero/tiptop_repro/cutamp_fluents.py:127-130`：

```python
elif pred == "inside" and len(args) == 2:
    if allow_approximations:
        _add(result, "on", args, pred, approximated=True,
             note="inside approximated as cuTAMP On(obj, container_surface)")
```

它把 `inside(X, region)` **原样**当成 `on(X, region)`，指望第二个参数自己是一个已存在的
placement surface。对抽屉场景这不成立：**真正存在、而且能解的表面叫
`wooden_cabinet_1_top_region_inner_floor`**，裸的 `wooden_cabinet_1_top_region` 从没被
materialize 成 surface。

报错的地方在 cuTAMP 的符号规划器
`$WORK/third_party/cuTAMP/cutamp/task_planning/search.py:275-285`（注意它是**在搜索开始之前**
的一道前置校验，注释自己写明"非 FABRICABLE_TYPES 的字面量必须已存在于初态，否则 BFS 会一直
展开新样本却永远满足不了目标"）：

```python
initial_literals_by_type: dict[str, set[str]] = defaultdict(set)
for atom in initial_state:
    for param, value in zip(atom.fluent.parameters, atom.values):
        initial_literals_by_type[param.type].add(value)
for atom in goal_state:
    for param, value in zip(atom.fluent.parameters, atom.values):
        if param.type in FABRICABLE_TYPES:
            continue
        if value not in initial_literals_by_type.get(param.type, set()):
            known = sorted(initial_literals_by_type.get(param.type, set()))
            raise ValueError(
                f"Goal atom {atom} references unknown {param.type} literal "
                f"'{value}' that does not appear in the initial state. "
                f"Known {param.type} literals: {known}"
            )
```

（所以之前 grep `unknown surface literal` 搜不到源码：那句话是 f-string 拼的，
源码里只有 `unknown {param.type} literal`。目标里的 `On` 首字母大写也是 cuTAMP 的
`Atom.__repr__`。）

也就是说链路是：BDDL `inside` → 我们的近似改写成 `on(…, region)`，把 region 名当 surface 名
→ cuTAMP 前置校验发现初态里没有这个 surface 字面量 → **抛 ValueError，搜索一步都没走**
→ `feasible=False, num_satisfying=0`。

证据是同一轮里 surrogate 目标

```
on(cheese, wooden_cabinet_1_top_region_inner_floor) + handempty
```

`feasible=True, num_satisfying=15`，Place IK 36/64，各约束
`robot_to_world 42/64 / movable_to_world 43/64 / robot_to_movables 62/64 /
StablePlacement ..._in_xy 36/64 / pos_err 62/64 / rot_err 62/64`。
也就是说**放置机制本身是通的，只是 BDDL 的真目标指向了一个不存在的名字**。

这不是偶发：仓库里已有两处同类的失败记录，
`skill_packs/libero90_legacy/skills/pair/recovery_hint/grounding/bowl_stack_support_grounding.md`
（"cuTAMP reports an unknown surface literal for the second bowl"）和
`skill_packs/libero_goal_swap_task07_seed51_65_v1/.../wine_rack_top_surface_geometry_explicit.md`
（"solves still failed with unknown surface literal `wine_rack_1_top_region`"），
后者的补救办法是用 `placement_region` geometry hint 把 region 名字 materialize 出来。

我们 pack 里其实也有对应草稿 `skills/fail_only/recovery_hint/geometry/cabinet_top_surface_geometry_explicit.md`，
但它写的是 bowl-on-cabinet-top 的 `wooden_cabinet_1_cabinet_top`，而且这些 hint 全在
`fail_only/`、`skills/_index.yaml` 是 `online: []`——本次运行的 `episode.json` 里
`skills_enabled: False`、`skill_pack: {}`，**一个 skill 都没加载**，所以没有任何 hint 生效。

两条可修路线（未做）：

1. 在 `inside` → `On` 的近似里把 region 解析成真实 surface：surface 上已经带着
   `source_bddl_region`（见 `real_cutamp_backend.py` 的 `_serialized_surface_openings`），
   按它反查即可，`wooden_cabinet_1_top_region` → `wooden_cabinet_1_top_region_inner_floor`。
   这是最贴近病根的一处，且证据齐备：同一个表面作为 surrogate 已经能解出 15 个粒子。
2. 走仓库既有的 `placement_region` geometry hint 路线，把
   `wooden_cabinet_1_top_region` 从当前抽屉 link（`wooden_cabinet_1_cabinet_top`，也就是
   `open_drawer_geometry_report.py` 报的 `drawer_link`）materialize 成 surface，并让 skill 真的加载
   （`--enable_skills`，或把 hint 提到 `pair/`）。

修好抓取之后新露出来的失败模式（这些以前被 0/64 挡在后面）：

```
[0] ops=['Pick'×4,'Place']  Place(...inner_floor):lift ok  :hover ok  :drop success=False  failure_reason='trajectory...'
[1] ops=['Pick'×4,'GoToInitial']  done=False
[2] ops=['Pick'×3]  execution_failed_stop reason='gripper_closed_but_not_holding'
[4] ops=['Pick'×4,'GoToInitial']  done=False
[5] ops=['Pick'×3]  execution_failed_stop reason='gripper_closed_but_not_holding'
[6] ops=['Pick']    execution_failed_stop reason='optimized_motion_budget_exhausted'
```

即：`Place:drop` 的轨迹执行失败一次、`gripper_closed_but_not_holding` 两次、
`optimized_motion_budget_exhausted` 一次。另外 `robot_to_world` 在若干 solve 里只有
62/64、42/64、31/64，说明 MoveHolding/Place 那层仍在丢粒子。

## 11. `inside` 目标失败的**最终**原因：抽屉当时是关着的

第 10 节把"名字对不上"当成病根，于是加了按 `source_bddl_region` 反查的解析
（`cutamp_fluents.map_atom_to_cutamp` 接受 `container_surface_resolver`，
`tamp_scene._container_surface_resolver` 提供实现，13 个单测覆盖，commit `3808826`）。
**这个解析本身是对的，但不足以修好它**——重跑之后 `mapped_goal` 仍然是未解析的
`on(..., wooden_cabinet_1_top_region)`，`resolved inside container` 一次都没出现。

原因在同一个 run 里两个 problem 的对比：

```
INSIDE(失败)     surfaces 10 个，没有 wooden_cabinet_1_top_region_inner_floor
                 out_drawer_place = [{status: "closed",
                                      reason: "drawer is not open; this skill does not open it"}]
ON(inner_floor)  surfaces 11 个，第 11 个就是 wooden_cabinet_1_top_region_inner_floor
(成功)           open_drawer_place = null
```

**两者不是同一个世界。** 失败的那个 problem 里，抽屉内底板这个 surface 压根不存在，
所以 resolver 正确地返回 None（没有可解析的目标），退回旧行为。而它不存在的理由，
`tamp_scene.py:1918-1933` 已经算出来并记在 `q_init_debug["open_drawer_place"]` 里了：

```python
for atom in goal_atoms:
    if atom.predicate in {"on", "inside"} and len(atom.args) >= 2 and atom.args[1] == name:
        placed_name = str(atom.args[0]); break
drawer_place = evaluate_open_drawer_place(scene, name, placed_name, ...)
if drawer_place is not None:
    if drawer_place["status"] == "ready":
        surfaces.append(...)      # 只有 ready 才建这个 surface
    else:
        open_drawer_refusals.append({...})
```

`place_in_open_drawer.evaluate_open_drawer_place` 在 `progress < OPEN_PROGRESS_MIN` 时返回
`status="closed"`，理由是"this skill does not open it"。于是链路是：

1. recovery 在 query 12 被强制唤起，抽屉**还没开**；
2. 目标 `inside(cheese, region)` 要求抽屉内部有一个放置面，而抽屉关着 → 按设计**不建**这个面；
3. 目标映射拿不到可解析的表面，只好把 region 名当表面名交给 cuTAMP；
4. cuTAMP 前置校验报"unknown surface literal" → `feasible=False`；
5. 控制器只看到 `real_cutamp_failure_reason` 是那句 ValueError——**全仓没有任何代码读
   `open_drawer_place` 这个拒绝**（`real_cutamp_backend.py` 里零命中），
   所以"抽屉没开"这个真正的原因被一个名字错误盖掉了，recovery 每个 episode 白试两次。

所以第 10 节"用 `placement_region` hint 把 region materialize 出来"这个方向在这里是**错的**：
抽屉关着时就不该有那个面。名字解析只在抽屉真开着的时候才有意义（那时它是对的，
且无副作用）。

两个仍未改的可选项：

* **A. 把拒绝如实报出来**：目标映射拿到 `open_drawer_refusals` 时，直接以
  `drawer_not_open` 之类的失败原因早退，而不是让一个不存在的名字撞进 cuTAMP。小、稳、
  只改"失败原因是否诚实"。
* **B. 处理前置条件**：抽屉关着时 recovery 拒答、把控制权交回 VLA，等抽屉真开了再被唤起
  做放置；或者让 recovery 自己去开抽屉（目前 `articulations: {}`，没有 articulation 能力，
  等于新功能）。

注意 `--force_recovery_query 12` 是强制在 query 12 唤起 recovery 的，所以 B 需要一个
"稍后再试/等前置条件"的机制，不是简单地换个 flag。

复现陷阱（重要）：**直接重解一个序列化过的 problem 无法验证这类修复**。目标是
`real_cutamp_backend.py:512` 从 `problem.fluent_mapping["goal"]["fluents"]` 读的，那是
problem 构造时录下来的映射；重解只会回放旧的（未解析的）目标，所以仍然报同样的错。
必须跑 live build（即完整评估）。

## 12. 两次连续 recovery：开抽屉的子目标出来了，卡在同类的起态碰撞

按"先开抽屉、再放"的方向实现（`real_cutamp_adapter.build_recovery_goal_candidates`，
commit `56e5814` / `8efcc66`）：复合目标（`select_drawer_inside_goal` 非 None）且抽屉未开时，
把 `open(<part>) + handempty` 作为**第一个**恢复目标候选，放在放置目标之前；抽屉是否要开
用 `find_drawer_joint` / `drawer_open_progress` + `OPEN_PROGRESS_MIN` 判断，与
`evaluate_open_drawer_place` 同一判据。

两个坑，第一个是首版完全没生效的原因：

1. **任务语言要求开抽屉，但 BDDL 目标里没有 `open` 原子**——目标只有
   `inside(cheese, region)` + `handempty`。所以 `articulated_goals` 是空的，首版
   （依赖 `articulated_goals`）一个目标都没发出来（`articulation_open` 命中 0 次）。
   改为**从 articulation binding 反推 part_id**（`_articulation_part_for_region`）。
2. 单测抓到两个真 bug：按 level token 兜底会把 `white_cabinet_1_top_region` 匹配给
   `wooden_cabinet_1_top_region`（不同柜子），改成前缀判定；"抽屉状态未知"原本被当成
   "需要打开"，与注释相反，改成不发目标。
   （`experiments/robot/libero/skill_pipeline/tests/test_drawer_open_before_place.py`，10 项）

跑 `open_drawer_run_open_then_place_20260927`（3 seed，加了
`--real_cutamp_articulation_config`，绑定取自
`$WORK/logs/articulation_top_20260923/binding_top.json`，即 part_id
`wooden_cabinet_1_top_region` / joint `wooden_cabinet_1_top_level` / handle geom
`wooden_cabinet_1_g18`）：

```
articulation_open_wooden_cabinet_1_top_region   命中 2 次   <-- 子目标确实发出来了
goals=['open(wooden_cabinet_1_top_region)','handempty()']  feasible=False  sat=0
failure_reason="ArticulationError:no_feasible_articulated_plan:
                 ['curobo_free_motion_failed:MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION']"
```

**`INVALID_START_STATE_WORLD_COLLISION`**——和本项目最开头那层（第 2 节）**同一类**问题：
articulation 求解的第一步是接近把手的自由运动，cuRobo 因为"起点构型已经与世界碰撞"直接拒绝。
第一次评估时用 `--start_state_retreat` 修好了普通求解路径，但那条退避没有作用到
articulation 路径上。于是：

* `open` 目标 2 次都不可行 → 抽屉没开；
* 抽屉没开 → 内底板 surface 不建 → `inside` 目标 5 次仍然报同一个
  `unknown surface literal` ValueError；
* episode：ep00 失败（61 查询 /300 步）、ep01 "成功"（13 查询 /61 步，但奶酪位移 0.000 m、
  全程未夹住，与第 9 节同类，不能算放置证据）、ep02 失败（奶酪移动 0.377 m，曾夹住）。

抓取那层仍然稳：`Pick 64/64` ×4、`Pick 32/64` ×4、`0/N` 出现 0 次。

下一步很明确：把已有的起态退避（`start_state_retreat.py` /
`RealCuTAMPBackend.retreat_from_start_collision`）接到 articulation 求解路径上——它现在只在
普通 `_solve_in_process` 路径生效。

### 12.1 只把 open 目标"排在前面"不够：它会被静默跳过

第一版把 `open` 候选加在放置候选**前面**（`add(...)`，候选 0）。结果仍然什么都没开：
articulated 求解被拒之后，planner **继续往后试**，而 `holding` 候选在抓取修好之后永远可行，
于是 recovery 报"成功"、去把奶酪抓起来，抽屉照样关着。更糟的是整个 recovery 看起来是 feasible，
**控制器的起态退避因此从不触发**，那个 `INVALID_START_STATE_WORLD_COLLISION` 也就永远没人理。

改成**只返回 open 这一个候选**（`return [RealCuTAMPRecoveryGoal(...)]`，commit `65e5586`）之后：

```
articulation_open_wooden_cabinet_1_top_region   命中 4 次
goals=['open(wooden_cabinet_1_top_region)','handempty()']  feasible=False  x6
recovery_diag: [9] outcome=retreat_executed  [10] outcome=no_feasible_plan
               [11] outcome=retreat_executed  [12] outcome=no_feasible_plan
```

**起态退避真的触发了两次**（这是之前从未发生的），但退避之后 open 目标仍然失败，失败原因一字未变：

```
ArticulationError:no_feasible_articulated_plan:
  ['curobo_free_motion_failed:MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION']
```

所以退避清掉的"起点碰撞"和 articulation 求解器自己看到的起点碰撞**不是同一个判据**：
普通路径的探针认为起点已经干净，而 articulation 的自由运动（`cutamp_articulation.solve` 里
`motion.approach(q, target, s)`，`q` 来自 `problem.q_init`）用的 cuRobo MotionGen 仍然报
起点与世界碰撞——很可能是 `articulation_curobo.CuroboArticulationMotion` 自己构造的 world
包含探针没有建模的几何（例如关闭状态下的抽屉内部/把手），或者它拿到的并不是退避后的构型。

顺带的行为变化（值得留意）：改成独占 open 目标后，ep01/ep02 的奶酪位移都变成 **0.000 m**
（之前是 0.429 / 0.400 m）——recovery 不再在抽屉关着时白白去抓奶酪了，这符合语义，
但也意味着那两次介入现在完全花在"开抽屉"上。episode 仍是 1/3，而那一次"成功"
是 13 查询 /61 步、奶酪位移 0.000 m，与第 9 节同类，不能算放置证据。

复现：`logs` 见 `$SSD/open_drawer_run_open_then_place_20260927`；
`why_retreat_missed.py`（本地 `.inspire/`）打印每个 recovery attempt 的
`retreat_skip_reason` / `retreat.executed` 与穿透量变化。

### 12.2 能力没问题，是喂进去的输入不一样

`$WORK/logs/articulation_top_20260923/` 里存着**同一个抽屉**解出来的原生计划
（`plan_wooden_top.json`：`GraspHandle → OpenArticulatedFromClosed → ReleaseHandle`），
所以"开抽屉能力"是存在且验证过的。把那份归档 problem 和我们 eval 里被拒的 open problem
并排比（`articulation_inputs.py`）：

| | 归档 smoke（成功解出） | 我们 eval（被拒） |
|---|---|---|
| goals | `open(part)` | `open(part)` + `handempty()` |
| `init_atoms` | **只有 `['handempty']`** | 完整符号态：`handempty, category, geometry_proxy, affordance…, open…` |
| movables / surfaces | **0 / 5** | **1 / 9**（奶酪 + 桌子/盘子/灶台/柜体各部件） |
| `q_init` | `[-0.008, -0.172, 0.007, -2.402, 0.016, 2.212, 0.789]` | `[-0.079, 0.537, -0.101, -1.612, 0.019, 2.186, 0.521]` |
| articulations | frame=`robot_base`、slide、`open=[-0.16,-0.145]`、`closed=[0,0.01]`、handle_geom=`wooden_cabinet_1_g18` | **完全相同**（同一 binding） |

**绑定、部件、行程、坐标系全一样**——能力参数是对的。差的是两样：
**(a) 起点构型**（eval 的 recovery 是 VLA 把手臂开过一段之后才被唤起的，smoke 用的是接近
home 的构型）；**(b) 世界规模**（eval 多背了奶酪和 4 个 surface）。
而报错恰好就是 `INVALID_START_STATE_WORLD_COLLISION`——"起点构型 × 世界"这一对，
正是上表唯一变了的东西。

另外两处待查的线索：
* eval 的 `init_atoms` 里**有一个 `open` 原子**，但 `_drawer_needs_opening` 依据关节位置
  判断为"未开"（否则不会发出 open 目标）——两者是否矛盾需要确认。
* `--solve-json` 那条 CLI 吃不下归档文件（封装格式不同，报 `KeyError: 'problem'`），
  要复现 smoke 需要直接调 `cutamp_articulation.solve_backend_problem`，
  或把归档内容包一层 `{"problem": ..., "config": ...}`。

下一步就是把这一个变量分开：用 smoke 的 `q_init` + eval 的世界跑一次，再用 eval 的 `q_init`
+ smoke 的世界跑一次，看是起点问题还是世界问题。

### 12.3 分离结果：世界没问题，**起点构型**才是墙

`variable_separation.py`（直接调 `cutamp_articulation.solve_backend_problem`，config 固定用
eval 的那份，只交叉 `q_init` 与世界）：

| 组合 | 结果 |
|---|---|
| **A** smoke 世界 + smoke `q_init`（对照） | `feasible=False`　`curobo_free_motion_failed:None` |
| **B** smoke 世界 + **eval** `q_init` | `feasible=False`　`articulation_ik_jump` |
| **C** **eval 世界** + smoke `q_init` | **`feasible=True`**　计划 `GraspHandle → OpenArticulatedFromClosed → ReleaseHandle` |
| **D** eval 世界 + **eval** `q_init`（被拒的那个） | `feasible=False`　`curobo_free_motion_failed:MotionGenStatus.INVALID_START_STATE_WORLD_COLLISION` |

**C 是关键**：在我们 task04 的真实世界（9 个 surface、含奶酪和灶台，比 smoke 的世界更大）
里，只要起点是 smoke 那个接近 home 的构型，**原生开抽屉计划就能解出来**。
B 和 D 都带 eval 的 `q_init`，都失败。

```
smoke q_init = [-0.008, -0.172, 0.007, -2.402, 0.016, 2.212, 0.789]
eval  q_init = [-0.079,  0.537, -0.101, -1.612, 0.019, 2.186, 0.521]
                     ^^^^^^          ^^^^^^
              joint2 差 0.71 rad，joint4 差 0.79 rad
```

所以结论是：**不是没有能力、不是世界太大、也不是绑定配错——是 VLA 把手臂开过一段之后，
那个起点构型下 articulation 求解器连"接近把手"的自由运动都过不了。** 能力在我们自己的场景里
是好的。

一个附带的重要限定：**A 也失败了**（`curobo_free_motion_failed:None`，status 是 `None` 而不是
枚举值），也就是说归档的那组输入在**当前分支的代码**上复现不出来——`plan_wooden_top.json`
是 `articulation-20260923` 那套代码产出的，当前分支的 articulation 实现与它不完全一致。
但 C 证明当前分支同样能产出这条计划，所以能力在，只是输入敏感。

可修方向（未做）：开抽屉之前先把手臂送到一个可达构型再求解——执行器里已有
`GoToInitial(q0)`（recovery 的算子序列里出现过），所以这是接线而不是新功能。
即把"两次介入"细化为：**回初始位 → 开抽屉 → 放置**。




