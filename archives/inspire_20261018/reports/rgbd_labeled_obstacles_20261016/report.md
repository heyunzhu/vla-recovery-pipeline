# 仅保留有标签障碍的恢复试验（2026-10-16）

按用户要求，对瓶子→碗的同一冻结现场，只保留当前检测器输出类别并由 SAM2 分割到的障碍表面。保留由深度测量的桌面、拟合的目标瓶子和已识别碗的支撑面/碗壁。未归属任何类别掩码的其余深度点不参与本次障碍规划。

这是一次明确改变障碍策略的实验，不改变默认路径。默认仍为 `all_observed_depth`；本次设置 `ANCHOR_LABELED_OBSTACLES_ONLY=1`，视觉入口增加 `--labeled-obstacles-only`。`observed_anchor_obstacles` 在原有桌面估计与目标/机器人归属之后，以当前有类别的分割掩码并集筛选剩余点；记录筛选前点数、保留点数及忽略点数。类别来自检测器预测，不是仿真真值标签，也不是自动按任务语言认定的类别。

## 对照与复现

- 对照：`rgbd_bowl_support_20261016/retry03/bowl_attempt03`，检测/拟合已通过，目标引用已修复，但恢复失败。
- 启智仅操作 `可上网GPU资源` 的 `xinghanbo-eval`，本轮开始时处于 RUNNING。
- 根目录 `ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo`。
- 新目录 `$ROOT/logs/rgbd_labeled_obstacles_20261016`；实际源码为 `code`，本次输出为 `bowl`。复制对照源码后应用本轮覆盖层，没有改历史日志、模型、冻结初始化或全局环境。
- 分支 `feature/rgbd-recovery`，基础 commit `62e4bc8410bcf1211c8b86dc8263746f2c8a6795`；实际执行还包含源码覆盖层，不能单凭基础 commit 复现。

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
EXPERIMENT="$ROOT/logs/rgbd_labeled_obstacles_20261016"
"$ROOT/envs/rlinf-openpi/bin/python" \
  "$EXPERIMENT/code/scripts/recovery/skill_pipeline/run_labeled_obstacle_replay.py" \
  --reference "$ROOT/logs/rgbd_bowl_support_20261016/retry03/bowl_attempt03" \
  --run-dir "$EXPERIMENT/bowl" \
  --code "$EXPERIMENT/code"
```

`--run-dir` 必须是未使用的目录。`bowl/command.json` 保存实际回放完整命令和环境覆盖；`bowl/experiment_manifest.json` 保存对照命令、初始化/BDDL SHA256 和源码 SHA256。检测权重、查询类别、阈值、640 分辨率、入口状态、控制器与规划预算全部沿用对照。恢复中继续屏蔽 simulator reward/done，最终 simulator success 仅用于评估。

## 验证与结果

本地 16 项相关测试通过，包括有标签障碍保留、无标签点忽略及桌面保留的新增测试。

**本轮能抓起瓶子，但没有完成“放进碗里”。** 原失败现场中初始瓶子碰撞告警消失，抓取恢复子目标有可行解并实际执行；完整放置目标仍规划失败，最终仿真任务评估为 false。

| 指标 | 原策略：全部剩余观测深度 | 本轮：仅类别掩码内剩余深度 |
| --- | --- | --- |
| 拟合瓶子、碗的几何 | 对照 | 与对照 JSON 完全相同 |
| 当前检测分割掩码 | 对照 | 与对照数组逐元素完全相同 |
| 剩余环境深度点 | 99511 | 83139，忽略 16372 点 |
| 静态碰撞盒总数 | 692 | 564 |
| 其中拟合碗壁盒子 | 188 | 188，全部保留 |
| 瓶盖 7 个残留像素 | 被视作环境障碍 | 7 个均在忽略掩码内 |
| 初始瓶子碰撞告警 | 有 | 无 |
| 放置目标求解 | 失败 | 仍失败，movable/world 和 StablePlacement 约束均有 0/64 |
| 回退抓取目标 | 无满足约束粒子 | 58 个满足约束粒子，可行并执行 |
| 实际选择的恢复目标 | 未成功执行 | `regain_target_holding` |
| 恢复器返回成功 | false | true，表示重新抓住目标的子目标成功 |
| 最终仿真任务评估 | false | **false，不能算完整任务成功** |

本轮合计 66 个环境步，其中恢复计划执行 61 步；实际执行列表只有 Pick，未执行 Place。末帧显示瓶子在夹爪中、碗仍为空。该结果支持“无标签残留障碍拖累抓取规划”，但没有证明忽略无标签物体就足以完成碗内放置，也不是十任务成功率结果。

优化没有固定采样种子，本轮是单次受控试跑；不能把两个随机求解结果差异直接当作成功率提升。

![最后状态：瓶子被抓起，碗内放置未完成](report_assets/final_bottle_held.png)

每帧的 `obstacle_semantic_masks.npz` 保存类别掩码并集、保留障碍点、忽略的无标签点及目标边界归属掩码；`ignored_unlabeled_obstacles.png` 用红色标出本轮实际忽略的点。

红色区域包括未被本帧检测器提名的盘子、奶酪盒及部分物体边界。红色只表示被实验策略忽略，并不表示这些区域没有真实表面。`retained_obstacle_pixels` 描述非目标环境剩余点；碗壁另由已识别碗的实测模型加入，并不在该剩余点掩码中。

![红色为本轮忽略的无标签深度点](report_assets/ignored_unlabeled_obstacles.png)

## 证据

- [实际回放命令与环境覆盖](rgbd_labeled_obstacles_20261016_command.json)。
- [结果与受控条件核验](rgbd_labeled_obstacles_20261016_summary.json)。
- 原始结果：`$ROOT/logs/rgbd_labeled_obstacles_20261016/bowl/finished.json`。
- 默认障碍策略保持不变；本次只在独立回放启用类别过滤，没有手动按碰撞盒编号删除对象，没有修改瓶子/碗几何或放置参数。
- [归档与实际执行源码的一致性证明](rgbd_labeled_obstacles_20261016_evidence.json)。服务器包为 `$ROOT/logs/rgbd_labeled_obstacles_evidence_20261016.zip`，62,447,614 字节，1579 个条目，SHA256 `7afa484323912e0a7ecc426c11f32bd450b148cb9a29faebd3ee7d6ff2218da5`。已下载到仓库 `analysis_outputs/rgbd_labeled_obstacles_20261016/recovery_evidence.zip`，核验 ZIP CRC、整体及内部 1578 个文件 SHA256；本地五个实现/测试文件与实际运行快照完全相同。
- 本轮实际运行库 HEAD 核验为 `7128c1ea6280c227e48561e621fe9da8604c5a6d`。外部模型、依赖与冻结控制器仍使用既有固定服务器资产；本证据包不是独立运行容器。
- 本轮回放已结束，实例保持运行。
