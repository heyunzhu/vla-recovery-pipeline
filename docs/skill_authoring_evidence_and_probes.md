# Skill 编写的证据与小验证

更新日期：2026-09-12

本约定适用于 repair、grasp、grounding、geometry、place。五类职责保持独立，
但同一次介入可以为同一条恢复链路补齐多个有依据的能力，不必等每层失败后才开始调查。

## 可以支持新增能力的证据

- rollout 的实际抓取、目标绑定、规划或执行失败；
- 对象尺寸、姿态、图像与默认采样代码共同显示候选不适合，例如薄盒的闭爪位置；
- BDDL 目标、scene object 和编译代码之间缺少必要映射，例如目标碗未被作为支撑面；
- 强制 query 小验证或 saved-problem replay 暴露的具体错误。

skills-off baseline 没有 recovery 记录是实验设置，不是后端能力充足的证据。
检查“切入后现有 backend 用哪个 grasp、绑定哪个目标、造什么几何、怎样释放”。
已有证据支持哪一层就修哪一层；不要求凑齐五类，也不能仅凭任务名称新增全部 profile。
未被验证的判断写成假设。图像对照应覆盖多个代表 ep，存在成功 ep 时加入成功对照。

## 固定工具

daemon 在每轮工作目录提供以下入口，输出全部留在本 run 的 mine/probes 下：

```powershell
python remote.py probe-recovery --seed 51 --query 10 --dry-run
python remote.py probe-recovery --seed 51 --query 10 --preflight-only
python remote.py probe-recovery --seed 51 --query 10
python remote.py check-drafts --draft-dir drafts
python remote.py probe-recovery --seed 51 --query 10 --draft-dir drafts
python apply_patch.py change.patch
```

probe 读取 lane_command.json，复用正式 eval_command：模型、suite、基础 seed、pack、GPU、
cuTAMP 参数、trajectory serialization 不重写，只改变强制 query、单 ep 切片和输出目录。
它同时保留 baseline 的 episode index 和 init_state_idx；seed57 对应 ep06 时不能重用 ep00。
旧 snapshot 不支持非零 episode 切片时会明确报错，不冒充同 init 验证。

Pi0/JAX 始终使用 lane.python_bin；cuTAMP 使用独立 planning Python 子进程。
不要手拼 run_skill_eval 命令，也不要使用 remote.py script --planning 启动完整 rollout。
--planning 仅用于保存的 cuTAMP problem，不是“所有 recovery 实验都用它”。
probe 与正式 validation 使用同一把 lane 锁，忙时返回 busy，不并发修改同一轮。

check-drafts 使用已有 parser、coordinator、静态 gate、pack code check 和 runtime profile
展开/注册检查。候选 patch 和 md 都安装到一次性副本，不改 active pack，不执行 ingest。
它没有替代全局离线扫描；后续 admission 仍执行原有全局扫描和正式验证。
禁止自己维护第二份 YAML 解析器、谓词名单或用文件长度代替既有检查。
change.patch 是 UTF-8 文件，使用工作目录相对路径；工具以参数传入真正的 patch 引擎，
不通过 PowerShell/Bash 拼接 patch 正文。

## 小验证结果如何使用

| status | 含义与处理 |
| --- | --- |
| infrastructure_error | 进程、解释器、依赖、初始状态或输出不完整；检查 plan.json、preflight.json、eval.log，纠正配置并重试，不能当物理失败。 |
| optimization_infeasible | 优化未满足条件；打开具体 problem/result/stderr，定位动作、目标和约束。 |
| motion_planning_failed | 运动规划失败；检查有满足粒子之后哪个运动段不可行。 |
| executable_plan_missing | 未得到可执行轨迹；检查优化产物到执行轨迹的转换。 |
| execution_failed | 已执行 recovery，但抓取、移动或释放失败；依据事件进一步定位。 |
| recovery_succeeded | 这一个诊断样本成功；可以继续验证在线触发，不代表泛化成功。 |
| recovery_not_entered | 没进入 recovery；检查 query 是否到达或任务是否提前结束。 |
| unknown_failure | 信息不足；继续读取列出的原始日志，不把汇总当根因。 |

一次 probe 可能包含多次规划尝试，汇总保留每次 result 和 stderr 的路径。
单个约束出现 0/64 不等于整条 episode 必然优化无解；先看具体失败阶段。

## 一次介入的交付

先形成可执行的接管假设，并取得一次真正进入待研究环节的小验证（结果可以失败），
或引用当前 run 已有、配置对应的有效 recovery 证据。不要为了获取第一次后端日志，
先消耗一版 repair 和一组正式 validation。小验证失败暴露其他层时，在本次介入内继续
检查和修复；无需提前宣布“只有 repair 问题”。修复检查错误不算新的 skill 版本。

findings 记录：观察、假设、源文件/图像、采用的代码路径、probe 结果路径、实际变化和
尚未验证的部分。未成功进入仿真不能写“验证已完成”，不能通过一句“缺依赖”结束调查。
基础设施确实不可用时保留草稿和错误说明，不编造物理结果、不擅改共享环境或引擎。

通过标准以本 run 配置为准。当前 task07 是 seed51-65 共15条、至少9成功（60%），
并且不能相对 baseline 退化。前5条全失败可早停拒绝，但不能用3/5替代9/15晋升。
probe/check 不调用 step/ingest/score，不递增 writes，也不直接更改 online。

## 本次工具验收

本地相关测试162项通过，覆盖命令继承、episode切片、不同失败阶段、候选副本、
profile展开后的能力注册、中文patch参数和调度器延迟切换。
2026-09-12 在现有 task07 run 下用 seed51、强制 q10 做了一次工具验收：

- preflight 使用 openpi_jax_py311 的 Python 3.11.15，etils/jax/openpi/mujoco 均可找到；
- 完整单 ep 已进入 recovery，返回 motion_planning_failed；它是可用诊断证据，不是技能成功；
- 输出目录为 /mnt/nas/gezuhao/xinghanbo/logs/libero_goal_swap_task07_actor_acceptance_20260912_r2/mine/probes/probe_xe6z9y4r；
- 原 baseline、当前 pack 与 writes 未由 probe 改动。

正在进行的介入使用它启动时冻结的文档。更新调度器时可用 --replace-idle-pid，
等待旧调度器完成当前介入后再接替，保留工作目录和事件，不直接中断 agent。
