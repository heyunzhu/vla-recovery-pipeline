# 正式规划后端接线与环境准备（2026-10-07）

## 代码接线

已将旧 `scene_reader` 中的 `ObjectState`、`JointState`、`SceneState` 移至不含传感器/模拟器读取的 `scene_types.py`。旧模块继续重导出同一组类型，保持oracle调用兼容。几何、符号状态、Panda坐标、TAMP场景等数据消费者改用纯类型模块。

在全新Python进程内，真实 `RealCuTAMPBackend` 和 `TAMPProblem` 能在 `OracleImportGuard` 下加载，三个禁止模块均不在 `sys.modules`，阻止导入次数为0。这只证明该导入链已拆开，不是完整运行时真值审计，也不代表已经求解。

现有后端增加 `initial_state_source='rgbd_observed'` 入口，实际调用 `visual_cutamp_state.build_observed_initial_state`。该模式不调用cuTAMP的默认初始状态生成器，不默认提供 `HandEmpty`；只消费带相同快照ID、RGB-D来源、明确置信度的显式 `HandEmpty`/`On` 观测事实。未知手中状态返回unknown，初始holding尚不支持，不能回退oracle。

`At(q0)`、`CanMove`、角色类型与本次规划的 `HasNotPickedUp` 是单独记录的规划域结构/程序状态，不伪装为视觉观测。旧配置默认保持 `legacy_simulator`，视觉正式入口仍需显式选择新模式并提供已验证事实。新入口尚未由在线runner调用。

## 验证

- 152项后端/旧执行兼容性测试通过。
- 16项共享视觉provider、规划输入与控制器测试单独通过。
- 完整 `skill_pipeline/tests`：**775项通过**，命令如下。

```powershell
& 'D:\大三上\科研\.venvs\rgbd-perception\Scripts\python.exe' -m unittest discover -s experiments/robot/libero/skill_pipeline/tests
```

首次在vla-dev环境全量执行发现Pillow缺失、Windows短路径/长路径比较不一致、oracle测试与视觉guard共用进程导致污染。已使用具有Pillow的现有感知环境；路径测试比较resolve后的实际文件；视觉guard场景移到全新子进程，保留生产guard和原有断言，不放宽禁止模块条件。随后全量通过。

cuTAMP初始状态测试使用接口兼容的fake fluents，证明新分支不消费默认状态、拒绝旧快照/非RGB-D来源、支持显式On和未知手状态；真实原生fluent与GPU求解仍待安装完成验证。

## 个人服务器环境

服务器已有 `/usr/local/cuda-12.8/bin/nvcc`（12.8.61），个人Python3.11.16、git-lfs和tmux。旧个人仿真环境有torch，但未安装cuTAMP/cuRobo。

按[cuTAMP官方安装说明](https://github.com/NVlabs/cuTAMP#installation)选择cuRobo v0.7.8；官方声明v0.8 API不兼容。源码版本固定：

| 源码 | 固定版本 |
| --- | --- |
| NVlabs/cuTAMP | `7932e6cf0ee216331e37e06b60f18bb8b3ec1fbd` |
| NVlabs/curobo | v0.7.8，`d64c4b005459db10c5dd867d8b30a87d5bda9bdb` |
| 传输tar.gz SHA-256 | `2140eedbaa3ffcb2be59817f25d418be5ab5fce3663aebdb73964026cba6157f` |

官方cuTAMP依赖声明限制 `warp-lang<1.13`，安装脚本沿用该上限。[官方依赖文件](https://github.com/NVlabs/cuTAMP/blob/7932e6cf0ee216331e37e06b60f18bb8b3ec1fbd/pyproject.toml)

个人目录：

- 环境：`/mnt/sdb/24_yyx/envs/cutamp-rgbd-20261007`
- 源码：`/mnt/sdb/24_yyx/projects/planning-vendor-20261007`
- 日志/阶段状态：`/mnt/sdb/24_yyx/setup/rgbd-planner-20261007/setup.log`、`status.txt`
- tmux：`rgbd-planner-setup-20261007`，启动pane进程PID236936。
- 本地启动脚本：`scripts/recovery/skill_pipeline/setup_rgbd_planner_personal.sh`。

截至本次记录，任务句柄仍活跃，阶段为 `torch_install`；临时下载产物由258MiB增长到361MiB，安装尚未完成。脚本选择torch2.7.1、初始numpy<2，设置CUDA_VISIBLE_DEVICES为空、编译目标sm89、MAX_JOBS=2，仅CPU下载/编译。未修改全局环境，未启动GPU实验；后续需实际核对最终依赖解析版本和原生模块加载，不把脚本意图视为安装成功。

服务器GitHub访问未及时返回，已终止该只读查询；源码通过本地官方下载和SCP传输，展开前两端摘要一致。没有因安装等待重新启动同一个任务。

## 尚未完成与后续

视觉几何到正式TAMPProblem的明确转换、视觉handempty/holding验收、可执行轨迹/闭环执行器和三入口生产接线仍未完成；在线成绩及A/B/C实验未开始。继续核对活跃安装任务，并开发视觉问题转换与运行时状态验收；GPU求解前再核对共享卡使用情况。
