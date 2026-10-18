# RGB-D 碗支撑几何扩展（2026-10-16）

本轮只验证瓶子→盘子的成功基线是否保持，以及瓶子→碗能否完整恢复。检测权重、语言、冻结物理状态和历史控制器均沿用上一轮；未重新训练，也未扩大到其他目标物。

## 固定资产与实验入口

- 分支：`feature/rgbd-recovery`；本地基础提交 `62e4bc8410bcf1211c8b86dc8263746f2c8a6795`，本轮代码是未提交覆盖层，不能仅凭这个 commit 复现。
- 服务器：启智 `可上网GPU资源` 的 `xinghanbo-eval`，本轮启动后节点 `qb-prod-4090-gpu177`。
- 根目录 `ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo`。
- 上轮成功源代码：`$ROOT/logs/rgbd_dino_integration_20261016/code_ownership8`，本轮复制后修改，原目录未改动。
- 新实验：`$ROOT/logs/rgbd_bowl_support_20261016`；`code` 是实际执行源码。`baseline_and_source_manifest.json` 保存基线命令、结果、运行库 HEAD 和新源码 SHA256。
- 历史运行库：`$ROOT/logs/continual_skill_core60_pilot_20261006/runtime_repo`，仍使用独立的 Python 3.11 仿真与 Python 3.10 规划环境。
- 检测器沿用 `rgbd_dino_integration_20261016/hf_export_best`，DINO 使用隔离 HF 4.40.2；SAM2、瓶子拟合、瓶子跟踪和上一轮的目标边界归属修复不变。

实验驱动：`scripts/recovery/skill_pipeline/run_bowl_support_regression.py`。它读取上轮保存的准确参数，先运行 `plate_regression`，再运行 `bowl_attempt01`。每个目录有独立的 `command.json`、`driver.log`、RGB-D 快照和结果文件；`progress.json`、`finished.json` 汇总完成状态。

在创建独立实验目录、复制成功源码并应用本轮覆盖层后，完整入口为：

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
BOWL_EXPERIMENT="$ROOT/logs/rgbd_bowl_support_20261016"
export ROOT BOWL_EXPERIMENT
"$ROOT/envs/rlinf-openpi/bin/python" \
  "$BOWL_EXPERIMENT/code/scripts/recovery/skill_pipeline/run_bowl_support_regression.py"
```

输出子目录必须尚不存在；上述目录已经执行过时应创建新的实验根目录。所有实际环境覆盖项和完整回放命令以各次 `command.json` 为准。

## 原卡点与改动

上一轮 `02_goal_bottle_bowl_640` 已提名瓶子和碗，语言绑定关系是 `inside`，但入口硬编码 `--fit-goal-plate`，随后因类别不是 plate 报错。因此那个结果没有验证碗的放置规划能力。

新增 `--fit-goal-support` 和 `ANCHOR_REPLACE_GOAL_GEOMETRY=1`：按视觉绑定的 plate/bowl 选择拟合器，旧盘子路径保留。碗模型只支持当前直立、近圆形、底部可见的碗与直立瓶子组合：

1. 用高处可见点拟合碗口圆，检查拟合残差和角度覆盖；缺少内底观测时拒绝拟合。
2. 用已拟合的瓶身半径测量碗底接触带高度，避免把最低点当作平底。当前只生成居中放置候选。
3. 内壁的观测点以 1 cm 分桶，生成观测点包围盒并增加 1 mm 数值厚度，作为独立静态碰撞体；没有填满整个碗，也没有补造不可见背面。
4. 支撑面是“居中直立瓶子接触高度”的水平近似，不是完整碗底重建，也不是通用容器模型。支撑物沿用初始 RGB-D 的静止假设。

冻结帧测量：碗口半径 0.05408 m、圆拟合 95% 残差 0.00127 m、12/12 方位分桶有观测；瓶身半径 0.02114 m；内底中心约 0.90677 m，瓶底接触带高度约 0.90852 m，碗沿约 0.94956 m。这些值来自 RGB-D 与分割掩码，没有读取碗的仿真碰撞几何。

![碗的观测点与瓶底接触高度](report_assets/bowl_measured_geometry.png)

## 验证与运行结果

本地相关测试 23 项通过，其中新增 3 项验证曲面接触高度、目标过大拒绝和内底遮挡拒绝。盘子是否保持成功以及碗能否恢复，必须以真实回放结果分别判断。

| 回放 | 结果 | 说明 |
| --- | --- | --- |
| `plate_regression` | 完整恢复成功，仿真最终评估成功，exit 0 | 122 个环境步，恢复中屏蔽 simulator reward/done；原物理状态精确恢复，没有加载 VLA。与上轮 139 步不同，不能据此声称所有随机规划轨迹完全一致。 |
| `bowl_attempt01` | 实验配置错误，exit 1 | 首版驱动错误复制盘子辅助类别表，`bowl` 与当前任务类别重叠，检测前被 `distractors cannot override task categories` 拒绝。这不计为检测或几何失败。 |
| `retry02/bowl_attempt02` | 恢复失败、最终评估失败，进程 exit 0 | 检测和几何成功，但旧 skill 将目标改为 `rgbd_bowl_obj_001_inner_floor`，视觉场景过滤仅允许实测碗 ID，删掉了旧代理支撑物。实际送入求解器的支撑物只有 table，目标仍指向已删代理。两次求解均无可行解；5 个环境步仅为入口动作。 |
| `retry03/bowl_attempt03` | 恢复失败、最终评估失败，进程 exit 0 | 实测碗支撑物与目标引用已一致，全部规划对象通过 RGB-D 来源检查；两次求解均无满足约束的粒子，未执行抓取。 |

`retry02` 使用独立源码副本和 `--bowl-only`，没有重写首轮源码 manifest。回归成功的盘子记录已保存；几何拟合通过不代表碗恢复成功。

第二轮确认为接口衔接问题，不能把其粒子初始化失败归咎于 DINO 或碗壁碰撞。第三轮在视觉 hook 内将已绑定的碗内放置编译为 `On(瓶子, 实测碗支撑面)`，语义审计仍记录 `inside`。只替换这两个视觉 ID 的放置目标，不更改旧 skill 的抓取/放置执行参数，不再生成第二个历史内底代理；规划前的 RGB-D 几何来源检查继续生效。实测碗壁新增 188 个碰撞盒，总计 692 个观测碰撞盒。

第三轮首个真实目标问题中，求解器同时包含 `table` 和 `rgbd_bowl_obj_001`，目标为 `on(rgbd_bottle_obj_002, rgbd_bowl_obj_001)`，已不再引用 `_inner_floor`。瓶子初始碰撞告警 cost 为 0.09718；机器人/物体碰撞、稳定放置和末端位置误差均出现 0/64 满足约束的记录。这些日志尚不能判定唯一根因。

### 瓶盖边缘的离线定位与对照

两个静态盒子 `rgbd_obstacle_0190`、`rgbd_obstacle_0216` 的原始计数分别为 2、5，总计 **7 个未归属的瓶盖边缘深度像素**。最初仅查询两个盒子的包围范围时会数到 8 个像素；其中一个已在瓶子掩码内，并不是残留障碍采样点。已按掩码与原始 counts 排除它，不能将 8 当作错误像素数。

这些点位于图像 `(row,col)`：`(232,268),(232,269),(233,267),(233,268),(233,269),(234,267),(235,268)`，距原瓶子掩码仅 1–2 像素。它们的深度高度约 1.05733–1.05780 m，而瓶子主连通面拟合的 top 为 1.05532 m。它们超出当前 `top + 2 mm` 归属上界约 0.001–0.473 mm，故保留成静态障碍；随后障碍的 2 mm 数值厚度在瓶颈顶部造成相交/近接触。这里的厘米级目标类别已经正确，剩余问题是分割小片段、拟合高度、表面归属和碰撞厚度之间的衔接。

![红色标记为两个残留障碍盒子的7个采样像素](report_assets/bottle_initial_collision_pixels.png)

在 `cap_collision_diagnostic` 中，针对第三轮同一个保存的规划问题做了 **仅离线求解、不执行动作** 的双条件对照。沿用历史脚本的变体名称 `no_mug`，但实际删除名单严格为上述两个盒子，没有删除碗壁或其他对象。控制器代码没有采用这种手动删除。

| 离线条件 | 初始瓶子碰撞告警 | 最终可行粒子 | 仍未通过的约束 |
| --- | --- | --- | --- |
| 原问题再求解 | 有，cost 0.06121 | 0 | robot/world、movable/world、稳定放置均出现 0/64 |
| 仅去掉这两个盒子 | 消失 | 0 | movable/world 仍为 0/64 |

因此两个瓶盖盒子确实是一个初始碰撞来源，但**不是所有失败的充分解释**。随机优化没有固定采样种子，其他约束记录的变化不能单独当作确定性修复证据。下一步应把可见瓶盖小片段纳入有证据的目标几何/归属，并定位余下 `movable_to_world` 碰撞发生在哪个阶段、哪一对物体；目前没有依据继续归咎于类别检测，也没有证明去掉两个盒子就能恢复成功。

盘子基线本轮最终 RGB 图像：

![盘子基线重跑成功](report_assets/plate_regression_final.png)

## 连接故障与恢复

启动实例后，SSH 自举多次失败于 `Failed to focus Jupyter terminal: xterm surface not ready`，直接 SSH 也超时。清理的仅是该实例的本地旧连接缓存。最终使用启智工具内置、无浏览器的 `run_command_capture_in_notebook` 终端接口成功执行命令并启动实验；没有操作其他实例或修改共享全局环境。实验后台进程启动 PID 为 75507。

## 归档与复核

- [五组实际执行命令与环境覆盖](rgbd_bowl_support_20261016_commands.json)：盘子、三轮碗回放、离线碰撞对照。
- [机器可读结果](rgbd_bowl_support_20261016_summary.json)。
- [归档完整性与最终源码一致性证明](rgbd_bowl_support_20261016_evidence.json)。
- 服务器证据包：`$ROOT/logs/rgbd_bowl_support_evidence_20261016.zip`，168,675,270 字节，4710 个条目，SHA256 `71854bcc97b065525720ea00d968904cfc4fc9bc71f8413b956cc18a9db95403`。
- 本地证据包：仓库下 `analysis_outputs/rgbd_bowl_support_20261016/recovery_evidence.zip`。已下载并验证整个包 SHA256、ZIP CRC 与内部 4709 个文件的逐文件 SHA256；本地最终四个实现文件与实际执行的 `retry03/code` 逐字节一致。
- 证据包包含三套实际源码快照、每次命令/日志/感知结果/规划问题/执行状态、两项冻结初始化，以及冻结运行库的 TiPToP 模块和 cuTAMP 包装脚本。模型大权重、外部依赖、仿真资产仍依赖上文固定服务器资产合同，不能把这个包视作独立可运行容器。

本轮没有扩展到十任务重测，也没有把离线删两个盒子的诊断当作恢复成功。实例保持运行，所有本轮回放与离线求解均已结束。
