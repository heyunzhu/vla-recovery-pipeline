# LIBERO-Pro：RGB-D恢复扩展实验（2026-10-15）

后续已完成统一10-task诊断批次，详见 [10-task卡点统计](rgbd_ten_tasks_20261015.md)。本文保留此前4例扩展与补跑记录，两个批次结果不混合计算。

## 结论

原酒瓶放盘子案例在重启实例后再次成功；新增同任务的 seed=2、init=1 恢复成功。当前完整视觉恢复证据因此覆盖酒瓶放盘子的两个初始状态，尚未扩展到新的任务语义。

另选的酒瓶放碗、碗放盘子、奶酪放架子，真值完整episode均重新跑通，但当前视觉恢复均在初始检测/绑定处失败。这些是从历史成功记录中挑选的诊断样本，不是随机抽样或held-out测试，不能用本表估计benchmark成功率。

## 样例与结果

任务编号为suite内部1-based；seed为episode seed，base seed均为90。恢复入口仍由冻结Pi0/C4流程触发。RGB-D列是从保存的入口物理状态重放恢复，不是从任务开始的端到端纯视觉VLA rollout。

| 样例 | Suite / task | ep / seed / init | 本轮真值完整ep | 正式RGB-D恢复 | 首个阻塞点 |
| --- | --- | --- | --- | --- | --- |
| 原酒瓶→盘子 | goal_task T4 | 0 / 1 / 0 | 复用10月9日已成功入口 | 成功，171步 | 无 |
| 新初态酒瓶→盘子 | goal_task T4 | 1 / 2 / 1 | 成功，1次recovery | 成功，123步 | 初次诊断试跑曾在放置后丢失跟踪；见下文 |
| 酒瓶→碗 | goal_task T7 | 1 / 2 / 1 | 成功，1次recovery | 失败 | `target_not_observed`，没有视觉瓶子候选 |
| 碗→盘子 | goal_swap T4 | 0 / 1 / 0 | 成功，1次recovery | 失败 | `goal_not_observed`，没有视觉盘子候选 |
| 奶酪→架子 | goal_task T8 | 0 / 1 / 0 | 成功，1次recovery | 失败 | `goal_not_observed`，没有视觉rack候选 |

完整suite名分别为 `libero_goal_task` 与 `libero_goal_swap`。原酒瓶T4的BDDL文件仍名为 `put_the_bowl_on_the_plate.bddl`，保留swap任务资产原名，不根据文件名猜实际语言。

两个成功运行均实际核验了solver输入：

| 运行 | 可行候选 | 后端秒数 | 静态RGB-D盒 | 保存视觉状态 |
| --- | ---: | ---: | ---: | ---: |
| `anchor_recheck` | 13 | 33.044 | 479 | 127 |
| `goal_plate_init1/visual_seed2_diagnostic` | 19 | 16.945 | 478 | 80 |

瓶子/盘子使用视觉ID，所有求解碰撞几何来源为RGB-D；reward/done对恢复屏蔽；恢复success与独立最终仿真评测均为true。机器人关节、末端、夹爪仍用本体信息。wine子类沿用受控案例人工确认，没有新增自动属性核实能力。

## 卡点证据

### 新初态的诊断失败与seed记录修正

第一个采集器版本在环境创建时记录seed=90，未跟踪runner随后调用的episode reseed=2。入口物理状态来自正确的ep01/seed2，且重放时精确恢复；但第一次视觉试跑reset使用了错误记录的90，因此不能纳入严格seed匹配结果。原fixture及失败日志完整保留，没有覆盖。

采集器已改为跟踪每次 `env.seed` 调用。后续三个样例分别记录正确的2、1、1。为第一个样例复制出 `fixture_seed2`，只修正seed元数据、不改物理状态数组，并保存 `metadata_correction.json`；用正确seed补跑，完整成功123步。两个物理状态数组的SHA256一致。

首次试跑并非简单规划失败：14个候选可行、抓取/抬升和搬运通过，到放置后退让时 `BottleColorDepthTracker` 抛出 `current RGB-D bottle tracking unresolved`。最后保存状态为步182，最后周期图像为步185。初次试跑未安装异常最终评测采集，因此没有该次终态真值成功标签，不能凭图像宣布任务已完成。

离线检查主视角可见瓶身颜色连通块：步175有408个深度点，固定半径圆拟合q95残差约0.705毫米；步180约2.761毫米；步185仍有439点，但q95残差约5.752毫米，超过当前5毫米门限。图像可见放置后姿态变化，证据与直立圆柱假设不再充分一致；不能简化成“整个瓶子都被遮住”。此结果说明当前姿态先验/跟踪拒绝机制仍有薄弱点，但不同reset seed及随机规划下的两次运行不是同条件稳定性统计。

离线诊断：`analysis_outputs/rgbd_expansion_20261015/init1_tracking_diagnostic.json`。

### 三个新任务：当前首先被检测/绑定阻挡

酒瓶放碗的主视角能看到部分瓶身，瓶颈受夹爪遮挡；Grounding DINO输出中瓶子相关框的文本分数未通过当前0.35文本门限，最终场景只有carton/stove/bowl类别。腕部视角使用同门限离线检查，仍为 `target_not_observed`。这说明直接换到这个已保存视角没有解决漏检，不能据此断言检测器完全不能识别瓶子。

仅将同一主视角文本门限降到0.25，会出现bottle候选，但同时出现两个bowl候选，绑定改为 `goal_ambiguous`。只降低门限没有形成可靠解。另一项碗放盘子在0.25下仍没有plate候选。上述敏感性检查只读保存图像，不调用求解器或执行动作，不计作恢复成功。

奶酪放架子的绑定为 `goal_not_observed`；没有进行该例的门限或视角扫描。首次失败来自视觉绑定，不能声称已测到该例的几何/执行能力。

检测拒绝后，诊断脚本仍继续寻找目标对象，产生 `StopIteration`；真正的上游原因已保存在提前写出的 `binding.json` 和 `visual_scene.json`。该异常传播方式也应改进为明确的状态拒绝。

即使未来检测修好，当前完整hook仍只装配bottle形状、plate支撑与瓶身颜色跟踪。碗/薄盒/rack/容器内放置所需的几何与执行语义还没有由这轮实验验证，不能把这些新任务的后端视为已支持。

## 版本、命令和产物

- 本地基础分支：`feature/rgbd-recovery`，基础HEAD `62e4bc8`，视觉成果代码提交 `31e7cd3`。
- 本轮增量尚未提交：扩展批处理脚本、episode/seed记录、失败时采集及检测结果提前落盘；没有调整感知模型、门限默认值、形状先验或规划参数来制造跨任务成功。
- 原重检直接使用10月9日成功冻结副本。
- 真值基线与视觉重放仍使用历史 `continual_skill_core60_pilot_20261006/runtime_repo`、C4包及模型环境；历史HEAD不能代替带本地补丁的冻结runtime。
- 平台仅操作 `可上网GPU资源/xinghanbo-eval`，从STOPPED启动，落在 `qb-prod-4090-gpu040`。未操作其他实例。全部实验进程结束后GPU利用率0%、显存23MiB，实例保持运行。

服务器根目录：`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo`。
本轮目录：其下 `logs/rgbd_expansion_20261015`。

每例的 `oracle/command.sh` 与 `visual/command.sh` 保存完整环境项、目录和命令。新初态正式成功命令在 `goal_plate_init1/visual_seed2_diagnostic/command.sh`。可从这些脚本复制参数到新的输出目录；直接重跑原目录会被防覆盖检查拒绝。

使用本轮冻结代码启动一轮新的同样选择样例：

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
SOURCE=$ROOT/logs/rgbd_expansion_20261015
NEW=$ROOT/logs/rgbd_expansion_repro_$(date +%Y%m%d_%H%M%S)
"$ROOT/envs/rlinf-openpi/bin/python" \
 "$SOURCE/expansion_code/scripts/recovery/skill_pipeline/run_rgbd_expansion_batch.py" \
 --root "$ROOT" --out-root "$NEW" --visual-code "$SOURCE/expansion_code"
```

冻结代码中的采集器已含seed修正；新的批次会直接按正确episode seed采集。上面命令会重新运行4个真值完整ep及对应视觉恢复，不能保证随机求解逐步一致。原锚点复现方式见 [完整复现说明](../rgbd_success_ep_reproduction_20261009.md)。

证据：

- [逐例核验摘要](rgbd_expansion_20261015_summary.json)。
- 服务器及本地均有 `evidence_complete.zip`；本地为 `analysis_outputs/rgbd_expansion_20261015/evidence_complete.zip`。
- 压缩包SHA256：`fdf6b970f081bee463a859c8bcb703538f7e278fee78b1585f23ae112ec0766a`，已核对远端/本地一致并通过CRC检查。
- 本地非源码提取目录：`analysis_outputs/rgbd_expansion_20261015/verified_evidence/`。完整源码在压缩包内保留，避免Windows长路径提取问题。
- 包含任务/seed/init清单、历史成功来源、BDDL/初态/pack哈希、原始命令、源码副本、真值episode与视频、RGB-D采样、绑定、拟合和求解文件、失败和成功记录。视觉代码symlink不重复打包，统一保存在包内 `expansion_code`；原始补丁zip另留服务器/本地。
- `batch_manifest.json` 的初始源码哈希对应批次启动版本；运行中仅修正seed记录与补充异常证据采集。首例原采集源码保存在自己的capture_support，后续采集源码与实际副本也保留，初始补丁保存在 `expansion_patch.zip`，不把初始哈希冒充所有阶段相同源码。

## 下一步

先固定现有两初态，补齐拒绝状态传播与放置后姿态变化的视觉检查，再改善遮挡下检测和多视角绑定；在得到可靠实例后，独立补上bowl、薄盒、rack的几何/执行接口。保持真值恢复为对照，不能把无观测的物体状态填成确定值。

## 软件检查

新增回归检查验证runner从base seed=90重设episode seed=2后，采集器记录更新为2，动作和步计数透传。`python -m unittest discover -s experiments/robot/libero/skill_pipeline/tests -p 'test_*.py'` 完成810项检查，全部通过；本轮5个修改/新增实验脚本均通过语法检查。这些软件检查不替代逐例服务器实验结果。
