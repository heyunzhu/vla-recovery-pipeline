# Live RGB-D visual adapter dry-run（2026-10-02）

## 本轮完成与实际结果

新增 `VisualDryRunAdapter`，提供 `query_state`、`perceive`、`executor_scene` 三个诊断接口，共用一个 `RGBDSceneProvider`。同一帧每次请求都验证完整 RGB-D digest，且任务语言不得在该帧改变；三个接口返回同一个 handoff 实例。`require_action_authorization` 始终拒绝规划和执行。检测异常直接传播，没有 oracle fallback。

新增 `run_live_visual_dry_run.py`，已在服务器个人目录实际完成一次 canary：task 0/init 1/seed 11、agentview 512、静置 10 步；LIBERO 环境保持存活并停止推进，本地冻结模型处理这一帧，检测 artifact 上传后服务器重新捕获保持帧并核对一致性，再依次消费三个接口和动作授权检查。与此前保存帧离线回放相比，本次验证了活着的仿真环境、外部检测返回与共享接口之间的交接。

| 验收项 | 实际结果 |
| --- | --- |
| 场景与语言绑定 | `visual_id_candidate`；target `obj_002`、goal `obj_003` |
| 检测配置 | 原冻结 silver ramekin 配置，`grounded-sam2-a62b7dbfbf7a`，4 个检测 |
| 三接口 handoff 是否为同一实例 | 是 |
| provider 检测后端调用次数 | 1（是 artifact 读取调用数，不是在线模型 FPS） |
| 检测等待期间环境是否推进 | 否，重采样完整 digest 验证通过 |
| 动作授权请求 | 明确拒绝 |
| guard 拦截的 oracle 导入尝试 | 0 |
| policy / recovery 动作 | 0 / 0 |
| 初始化空动作 | 10 |
| 正式 runner/perceiver/executor 接入 | **尚未完成** |

`black bowl` 属性、物体/抓取几何、目标区域/净空、持物与目标验收仍是 handoff 未解决项。既无恢复动作，也无恢复成功率。

机器结果见 [live dry-run 报告](rgbd_live_dry_run_report_20261002.json)。报告明确记录 `production_runner_integrated=false`，不能把独立 adapter 的三接口同一实例验证写成已替换正式评测的三个 oracle 入口。

## 真值访问检查的范围

新增进程级 `OracleImportGuard`，在 canary 中禁止导入以下模块；若它们已在 guard 启动前导入，则拒绝启动：

- `experiments.robot.libero.tiptop_repro.scene_reader`
- `experiments.robot.libero.tiptop_repro.cutamp_controller_v2`
- `experiments.robot.libero.tiptop_repro.libero_tiptop_executor`

单元测试明确尝试导入 `scene_reader` 并确认抛错、计数增加及退出后恢复 import 状态。实际 canary 中拦截次数为 0。**这是一项针对命名模块导入路径的检查，不是全进程任意 MuJoCo 内存读取审计。** 仿真本身的动力学与任务初始化仍依赖环境内部状态；sensor 允许读取相机标定、深度转换参数、时钟和白名单本体观测。当前 adapter 不接受 env/sim 参数，其视觉决策只消费 RGB-D 和冻结 mask。

本次没有加载 VLA、旧 oracle planner 或执行器。完整的零 oracle 决策依赖验证仍需在正式 runner 接入时，对各入口和非相机状态访问做集成门槛。

## 可复现工作流

1. 在个人 LIBERO 环境运行新脚本，指定冻结提示词与新的输出目录。脚本先采集 `observation/` 和 `summary.json`，打印 `VISUAL_FRAME_READY`，然后等待 `detector/READY`，默认最多 600 秒。
2. 在保留该环境进程的同时，复制观测到已配置冻结模型的机器；用 `run_grounded_sam2_snapshot.py --prompts-json` 处理当前 observation，固定权重与阈值。
3. 将完整 `run_config.json`、`detections.json`、`detections.npz` 交回该 live 输出目录的 `detector/`。全部上传成功后才写 `READY`。服务器核对提示配置、图像大小、config 哈希生成的 detector ID、RGB 哈希及帧身份，避免加载未传完的结果。
4. 脚本验证三接口缓存和动作拒绝，写出 `dry_run_result.json`，打印完成信息，关闭环境。异常或超时也关闭环境；不会自动运行 oracle recovery。

远端本次命令（需保持此进程，在另一终端完成检测/上传）：

```bash
LIBERO_CONFIG_PATH=/mnt/sdb/24_yyx/config/libero \
PYTHONPATH=/mnt/sdb/24_yyx/projects/LIBERO-f78abd68ee283de9f9be3c8f7e2a9ad60246e95c:/mnt/sdb/24_yyx/projects/visual-dry-run-runtime-20261002-v2 \
/mnt/sdb/24_yyx/envs/libero-official/bin/python -u \
  scripts/recovery/skill_pipeline/run_live_visual_dry_run.py \
  --task-suite-name libero_spatial --task-id 0 --init-index 1 --seed 11 \
  --resolution 512 --settle-steps 10 --prompts-json frozen_prompts.json \
  --out-dir /mnt/sdb/24_yyx/demo/live-visual-dry-run-replay-new
```

输出目录必须未存在。该 script 目前只为普通 task language canary 验证，不承担正式 BDDL language/goal runner 功能。

## 产物、部署与测试

服务器 runtime 在 `/mnt/sdb/24_yyx/projects/visual-dry-run-runtime-20261002-v2`；结果在 `/mnt/sdb/24_yyx/demo/live-visual-dry-run-20261002`；本地同名结果副本位于 `D:\大三上\科研`。源码包 `visual_dry_run_runtime_20261002_v2.zip` 的 SHA-256 为 `f37175e17dfb3e8c22b672d2f724d65f881296bf21ba2cfd9aab8bfb115141a3`，远端解包前核验 archive、解包后逐文件核验 manifest。见 [源码 SHA-256 清单](rgbd_live_dry_run_source_sha256_20261002.json)。

首次精简包启动因缺少包初始化依赖 `adapter_discovery.py` 失败，当时尚未创建环境或实验输出。补齐依赖后使用新 v2 runtime 完成 canary，旧运行包保留；没有修改共享工作树或全局环境。服务器使用 Python 3.8 / robosuite 1.4.1，本地检测使用既有 CPU 模型环境。

完整 skill-pipeline 测试 **589 项通过**。新增测试覆盖接口同快照/动作拒绝、输入或语言改变拒绝、检测失败不回退、mask 冲突拒绝，以及 oracle 导入 guard。

## 下一步

将正式 runner 的状态查询和 perceiver/executor 读取统一路由到明确版本的 visual adapter，先保持 dry-run，仅记录哪些现有 qstate/planner 字段尚不能由视觉提供。对缺少类别属性、几何、holding 或碰撞信息的请求明确拒绝；禁止转换可见质心为真值 body pose 或进行 oracle fallback。通过入口集成检查后，再引入可执行几何代理和小范围恢复动作验证。
