# LIBERO Goal Task 01 下层抽屉迁移验证

日期：2026-09-29
结论：Task 7 的下层抽屉能力不能原样复用；经过局部位姿搜索、短拉真值门和夹紧调整后，Task 01 已得到由 recovery 自身完成的闭环成功，并在 seed 51--65 的 15 个初始化状态上取得 14/15 的 recovery 成功率。

## 1. 任务与验收口径

目标语言是 `open the bottom drawer of the cabinet`。LIBERO-Pro 注册表中的 task01 文件名是 `open_the_middle_drawer_of_the_cabinet.bddl`，但文件内 `:language` 和目标谓词实际指向 bottom drawer；本次运行固定使用 `--task_language_source bddl --engine_language_source bddl`。

成功不能只看 episode 的最终 `success`。正式验收要求 recovery trace 中的 `open(wooden_cabinet_1_cabinet_bottom)` 执行事件本身成功，并且实测 joint 进入目标区间。这样可排除 recovery 失败后由 VLA 偶然补完的假阳性。

## 2. 最终成功结果

- 配置：`experiments/robot/libero/tiptop_repro/configs/libero_goal_task01_bottom_drawer_open_v1.json`
- profile：`bottom_drawer_goal_task01_height6_tight_v1`
- skill pack：`skill_packs/bottom_drawer_articulation_v1`
- profile skill：`open_bottom_drawer_geometry_auto`（由实时几何选择本 profile）
- task / episode / seed：task01 / ep00 / 51
- recovery 执行结果：`success=true`
- 实测最终 joint：`-0.1401520520`
- 目标区间：`[-0.16, -0.140001]`
- recovery 环境步数：`616`
- 运行预算：`--max_recovery_steps 900`
- 服务器证据：`/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task01_drawer_20260928/task01_probe_roll25_height6_tight_budget900_seed51`

末端最后一个 Cartesian waypoint 的位置误差约为 8.05 mm，控制器报告未完全到位；但此时实测抽屉 joint 和环境任务谓词均已满足，所以 articulation executor 按任务状态返回成功。这不是轨迹假成功，也没有直接修改 drawer qpos。

## 3. 抓法是怎样找到的

初始尝试直接迁移 Task 7 的 candidate 8。语义绑定、part/joint/handle 识别、cuRobo IK 和完整 slide 路径都能工作，但原抓法在 Task 01 上只是短暂接触把手，长拉时末端离开而抽屉不跟随。

随后把抓法搜索从单一 roll 扩成 handle frame 中的局部位姿网格：

- roll：相对当前候选 `-10° / 0° / +10°`；
- handle-frame x：`-6 / 0 / +6 mm`；
- handle-frame y：`-6 / 0 / +6 mm`；
- handle-frame z：本轮固定 `0 mm`。

27 个候选中有 18 个通过严格 approach 和完整 15 cm slide 的离线运动学/碰撞检查。报告保存在：

- 服务器：`/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task01_drawer_20260928/task01_local_pose_grid_20260929.json`
- 本地证据目录：`E:\VLA_recovery_workspace\remote_outputs\libero_goal_task01_drawer_20260928\task01_local_pose_grid_20260929.json`

物理仿真进一步给出了三条关键边界：

| 候选 | 结果 | 结论 |
| --- | --- | --- |
| 原 roll25 / 外移 6 mm | 双侧接触后长拉无进度 | 接触存在，但没有形成可保持的包络 |
| 再向把手深入 6 mm | approach 停在目标前约 11.6 mm | 深度越过可执行接触边界 |
| 原深度 / 抬高 6 mm | 短拉能带动抽屉，长拉后滑脱 | 高度修正改善了接触拓扑 |
| 抬高 6 mm / squeeze 2 mm | 16.8 mm 短拉中 joint 实际移动 12.9 mm | 有效夹持成立；600-step 预算不足 |
| 同上 / 900-step 预算 | recovery 独立成功 | 最终正式候选 |

最终抓法相对上一版失败候选的核心变化不是继续增加 roll，而是沿 handle frame 抬高 6 mm，使夹爪更可靠地包住把手；同时将 squeeze half-width 从 5 mm 收紧为 2 mm。

## 4. 新增的通用执行门

profile 可选字段：

- `contact_probe_distance_m`：完整拉动前先执行的短拉距离；
- `contact_probe_min_progress_m`：短拉后 drawer joint 必须达到的最小真实进度。

本配置先拉 15 mm，并要求实测 joint 至少同向移动 4 mm。若不满足，执行立即返回 `handle_contact_probe_no_progress`，避免把瞬时双侧接触误判为有效抓取。成功和失败日志都会给出 start、actual、expected 和 measured joint progress。

该门只在 profile 显式设置时启用，不改变已经验证的 LIBERO-90 Task 7 profile。

## 5. 代码修正与诊断工具

- 修正 contact-induced stall 已被接受后，执行器仍错误终止后续 waypoint 的控制流问题；
- `probe_articulation_refine.py` 现在使用真实 `path_settings`，检查严格 approach、joint jump、dense slide collision，并报告首个无效状态；
- refine probe 支持 roll 与 handle-frame xyz offset 的组合网格，并为完整可行候选输出 grasp matrix；
- articulation executor 增加短拉真实进度门和更具体的 joint 误差日志。

本地回归：`python -m unittest experiments.robot.libero.skill_pipeline.tests.test_articulation`，41 个测试通过，其中 6 个因本地没有原生 cuTAMP 依赖而跳过。

## 6. 当前能力边界

### 6.1 seed 51--65 泛化回归

使用相同 Task 01 profile 连续运行 15 个 episode，episode seed 为 51--65，init-state index 为 0--14。每轮在 query 0 强制进入一次 recovery，recovery budget 为 900。结果如下：

| seed | init state | recovery | 最终 joint | recovery steps |
| ---: | ---: | :---: | ---: | ---: |
| 51 | 0 | 成功 | -0.140152 | 616 |
| 52 | 1 | 成功 | -0.140795 | 627 |
| 53 | 2 | 成功 | -0.140204 | 606 |
| 54 | 3 | 成功 | -0.140005 | 612 |
| 55 | 4 | 成功 | -0.140969 | 635 |
| 56 | 5 | 成功 | -0.140272 | 658 |
| 57 | 6 | 成功 | -0.140874 | 614 |
| 58 | 7 | 成功 | -0.140908 | 667 |
| 59 | 8 | 失败 | 未记录 | 584 |
| 60 | 9 | 成功 | -0.140186 | 655 |
| 61 | 10 | 成功 | -0.140872 | 615 |
| 62 | 11 | 成功 | -0.140831 | 612 |
| 63 | 12 | 成功 | -0.140823 | 620 |
| 64 | 13 | 成功 | -0.140710 | 621 |
| 65 | 14 | 成功 | -0.140217 | 613 |

- recovery 严格成功率：14/15（93.3%）；
- episode 最终成功率：14/15（93.3%），与 recovery 结果逐项一致，没有 VLA 补完造成的假阳性；
- 14 次成功的环境步数范围为 606--667，平均 626.5；
- 14 次成功的 joint 均进入 `[-0.16, -0.140001]`，终值范围为 `[-0.140969, -0.140005]`；
- 15 次短拉接触探测均通过。seed 59 的短拉 joint 进度为 13.922 mm，说明它已经抓住并带动抽屉；失败发生在后续长拉阶段，而不是语义绑定、cuTAMP approach、IK 或初始接触阶段；
- seed 59 的长拉仅覆盖部分路径，结束时末端位置误差约 32.59 mm，返回 `optimized_motion_pose_not_reached`。因此当前唯一暴露出的泛化薄弱点是个别初始化下的长拉执行裕量，而非固定抓取位姿完全失效。

完整 trace 和 15 个视频保存在：

- 服务器：`/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task01_drawer_20260928/task01_generalization_seed51_65_20260929`
- 本地：`E:\VLA_recovery_workspace\remote_outputs\libero_goal_task01_drawer_20260928\task01_generalization_seed51_65_20260929`

### 6.2 能力边界与下一步

该结果支持“同一 Task 01、跨 15 个初始化状态”的场景内泛化，但仍不能宣称跨柜体或跨任务的稳健泛化。下一步准入应至少增加：

1. 对 seed 59 做定点复现，判断增加长拉预算、减小 tracking waypoint 间距或在长拉中按 joint progress 提前结束，哪一种能消除失败；
2. LIBERO-90 Task 7 回归，确认新增执行逻辑没有退化；
3. 将 `--max_recovery_steps 900` 固化到该能力的运行规格或预算选择策略；
4. 只有上述回归稳定通过后，才把 Task 01 profile 合并进更广义的 bottom-drawer 能力包。

`ignore_drawer_environment_overlap=true` 只关闭规划器中保守的 moving-drawer/fixed-object box-overlap 代理检查；MuJoCo 物理碰撞、机器人碰撞检查、真实 handle contact 和 joint progress 均仍保留。此次成功没有删除 plate、bowl 或其他场景物体。
