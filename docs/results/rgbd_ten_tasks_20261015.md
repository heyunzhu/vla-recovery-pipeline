# LIBERO-Pro：10-task RGB-D恢复卡点统计（2026-10-15）

## 结论

统一批次的10个不同task全部完成；本轮真值完整episode成功 **7/10**，从各自恢复入口重放的RGB-D恢复完整成功 **1/10**。两者测试阶段不同，不将该差值作为端到端策略收益。

视觉侧首个可观察卡点：**7例未形成可绑定候选，1例几何类型未支持，1例语言解析未支持**；成功例仍是酒瓶放盘子。当前优先阻塞在前端与接口覆盖，不能将未到达的规划/执行层记作通过。

## 逐任务结果

所有任务在运行前固定；均已从历史轨迹核查到成功的恢复执行完成事件。每个task一个episode/seed/init，不按本轮结果替换任务或重跑已完成失败样例。suite/task编号是唯一身份，任务语言也各不相同。

| # | 任务 | Suite / task | ep / seed / init | 本轮真值ep | RGB-D结果/首个卡点 |
| --- | --- | --- | --- | --- | --- |
| 1 | 酒瓶→盘子 | `libero_goal_task` T4 | 0/1/0 | 成功 | 完整成功，139个恢复环境步 |
| 2 | 酒瓶→碗 | `libero_goal_task` T7 | 1/2/1 | 成功 | 缺少瓶子候选 |
| 3 | 奶酪→架子 | `libero_goal_task` T8 | 0/1/0 | 成功 | 缺少rack候选 |
| 4 | 碗→盘子 | `libero_goal_swap` T4 | 0/1/0 | 失败 | 缺少plate候选 |
| 5 | 奶酪→碗 | `libero_goal_swap` T7 | 0/1/0 | 失败 | 缺少bowl候选 |
| 6 | 奶酪→篮子 | `libero_object_task` T1 | 0/1/0 | 成功 | 缺少basket候选 |
| 7 | 果汁→篮子 | `libero_object_task` T3 | 0/1/0 | 成功 | 缺少basket候选 |
| 8 | 牛奶→篮子 | `libero_object_task` T6 | 0/1/0 | 成功 | 缺少basket候选 |
| 9 | 靠近盘子的黑碗→盘子 | `libero_spatial_task` T2 | 4/5/4 | 失败 | bowl目标被瓶子专用形状接口拒绝 |
| 10 | 柜顶黑碗→盘子 | `libero_spatial_task` T3 | 0/1/0 | 成功 | 不支持目标短语中的on/top/of空间关系 |

## 汇总口径与到达层数

| 互斥结果 | 例数（分母10） |
| --- | ---: |
| 完整视觉恢复成功 | 1 |
| 检测/可绑定候选缺失 | 7 |
| 几何类型未支持 | 1 |
| 语言解析未支持 | 1 |

7例候选缺失包括1例目标瓶子未观察到、6例目标支撑物未观察到。这是绑定器的直接拒绝原因；它可能涉及可见性、模型框、文本标签映射、分数过滤或掩码质量，不等同于已测得检测器分类错误率。外层的 `StopIteration` / `CalledProcessError` 是下游异常包装，按提前保存的 `binding.json` 追溯上游原因。

| 有对应产物的阶段 | 到达任务数 |
| --- | ---: |
| 导出视觉场景 | 9 |
| 形成目标/goal绑定候选 | 2 |
| 瓶子形状与盘子支撑均准备完成 | 1 |
| 调用原生求解且可行 | 1 |
| 完整恢复与独立评测均成功 | 1 |

其中形成候选只表示有可用ID，不代表全部属性已自动核实。wine子类仍是受控案例人工确认。失败样例只计首个有证据的卡点，后续层标为未测试，不重复计数。

只看本轮真值成功的7例：视觉完整成功1例，候选缺失5例，语言解析失败1例。因此真值侧的3例失败不能解释其余全部视觉失败。几何类型失败的空间关系样例本轮真值也失败，已保留此限制，不把它用于声称纯感知的因果退化。

## 具体卡点

### 前端候选缺失

酒瓶放碗缺少bottle；奶酪放架子缺少rack；碗放盘子缺少plate；奶酪放碗缺少bowl；三个篮子任务均缺少basket。各例已保存RGB-D、检测框、分割、视觉场景和绑定原因。不能仅凭这些拒绝原因判断是物体不可见还是模型/过滤失败，下一轮宜在固定帧上逐步检查框、标签、掩码及绑定，再运行动作。

### 几何类型接口未支持

空间关系任务T2形成了bowl与plate候选，但当前完整恢复hook仍启用 `--fit-target-bottle`。诊断脚本明确报 `bottle fitting requires a visually nominated bottle`，没有用瓶子模型冒充碗。这属于形状提供器覆盖不足，不是一次碗形状拟合精度实验。即便前端修好，薄盒、纸盒、bowl、basket/rack及inside目标也需要各自经验证的几何/执行接口。

### 语言解析未支持

柜顶任务的目标短语为 `akita black bowl on the top of the wooden cabinet`。当前简化语言解析器不支持该空间关系表达，模型检测尚未运行就已拒绝。不能将这一例计为检测器漏检。

## 真值侧失败

历史成功不保证新一轮随机求解/执行仍成功。本轮3个失败真值episode也完整保留：

| 任务 | 可行求解输出份数 | 记录到的执行异常 |
| --- | ---: | --- |
| 碗→盘子 | 3 | 抬升后持物未确认、闭爪未持物、运动预算耗尽、轨迹停滞、hover未对齐 |
| 奶酪→碗 | 1 | 轨迹停滞/跟踪预算耗尽、hover未对齐 |
| 靠近盘子的黑碗→盘子 | 3 | 抬升后持物未确认、闭爪未持物 |

这些是日志中的异常，不声称每项都是独立根因。过程中正常出现的 `goal_atoms_not_yet_satisfied` 不作为关键执行错误计数。真值结果与视觉结果分列，原始10行不删除；JSON同时提供本轮真值成功的可比较子集。

## 配置、执行与中断

- 仅操作启智 `可上网GPU资源/xinghanbo-eval`；沿用冻结Core-60 runtime、C4技能包、Pi0及cuTAMP配置。
- 初始本地基础分支 `feature/rgbd-recovery`，基础HEAD `62e4bc8`；原视觉成果代码提交 `31e7cd3`。本轮新增批处理/统计/恢复辅助脚本为工作区增量，不能只靠该HEAD复现实验。
- 视觉代码在批次开始时冻结到独立目录，全部任务使用相同模型及0.35文本门限；未在中途修改视觉逻辑、形状假设或技能。所有冻结视觉Python源码、关键runtime文件及pack文件的前后SHA256均一致。
- 真值从任务开头运行Pi0并自然触发恢复，保存首次恢复入口。视觉从该物理状态重放；10个fixture的episode seed均与选定样例一致，夹爪控制指令按测量张开重建，没有完整控制器内部checkpoint。
- 视觉侧六个替换开关全部开启，启用 `--evaluation-done-only`。完整成功例已重新检查：物体使用视觉ID，所有原生碰撞几何来源RGB-D，不关联仿真物体名，仿真reward/done对恢复屏蔽，最终仿真成功只作评测标签。
- 11:04:07（北京时间）实例被平台preempt/evicted，从 `qb-prod-4090-gpu040` 调度到 `qb-prod-4090-gpu026`。保留第1例已完成结果，归档第2例中断现场，再恢复未完成部分；中断本身不计为机器人失败。已完成失败不会被重跑筛选掉。
- 后续CLI Web认证检查返回404；现有授权SSH缓存连接仍可使用，通过同一Inspire库的连接执行/下载能力完成读取。未改账号凭据或其他实例。
- 完成后GPU利用率0%，显存21MiB；实验进程已结束，实例保持运行。

这是选定历史成功样例的一轮诊断，不是随机抽样、held-out泛化或稳定成功率估计。真值完整ep与视觉恢复重放也不具有相同测试范围；本轮没有验证从任务开头的端到端纯RGB-D VLA系统。

## 命令、源码和证据

服务器根目录：`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo`。本轮在其下 `logs/rgbd_ten_tasks_20261015`。每例保存 `oracle/command.sh` 和 `visual/command.sh`，批次命令在 `batch_command.json`，恢复命令在 `resume_command.json`。

用同一冻结视觉版本启动新的10-task批次（新目录，不覆盖原结果）：

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
SOURCE=$ROOT/logs/rgbd_ten_tasks_20261015
NEW=$ROOT/logs/rgbd_ten_tasks_repro_$(date +%Y%m%d_%H%M%S)
"$ROOT/envs/rlinf-openpi/bin/python" "$SOURCE/resume_batch_driver.py" \
 --root "$ROOT" --out-root "$NEW" --visual-code "$SOURCE/visual_code_frozen" \
 --cases-json "$SOURCE/cases.json"
"$ROOT/envs/rlinf-openpi/bin/python" "$SOURCE/summarize_rgbd_task_batch.py" \
 "$NEW" --out-dir "$NEW/statistics"
```

若发生平台中断，确认原进程已结束后，可用同一批次参数加 `--resume`。恢复器验证任务选择与冻结视觉源码哈希一致，保存完成的成功及失败，将中断目录移到批次内部的 `interrupted_runs`；结果写入采用原子替换。

- [逐task CSV](rgbd_ten_tasks_20261015_task_blockers.csv)。
- [机器可读统计摘要](rgbd_ten_tasks_20261015_summary.json)。摘要不内嵌大型attempts，完整结果在证据包。
- [运行前冻结的10-task选择](rgbd_ten_tasks_20261015_cases.json)。
- 服务器证据包：上述目录的 `evidence_complete.zip`。
- 本地证据包：`analysis_outputs/rgbd_ten_tasks_20261015/evidence_complete.zip`。
- SHA256：`02015d5aec9826863c67b0cc8ec8465ace47b10f4a1d91652766eabe7e94a45c`。远端/本地一致，CRC检查通过。
- 非源码提取目录：`analysis_outputs/rgbd_ten_tasks_20261015/evidence/`；源码完整保留在zip内，避免Windows长路径。
- 包含历史10例episode/恢复轨迹副本、任务manifest、源码/pack/runtime哈希、fixture与seed检查、真值及视觉运行日志、视频、RGB-D、检测绑定、求解/执行记录、平台中断及恢复记录、最终核验。

## 软件检查

820项核心测试全部通过；统计及中断恢复的针对性检查通过，覆盖：保留10个失败样例分母、绑定拒绝先于包装异常分类、可行计划不冒充完整成功、完成判据与评测不一致、运行中样例不算完成、完成失败不重跑、中断文件不丢失。后续仅将统计JSON中的大型attempts改为原始产物引用，未改分类或计数。
