# 原生后端安装、CPU世界与首次GPU结果

2026-10-07。本次完成实际运行验证，但未完成在线恢复。

## 实际安装与CPU世界

个人环境 `/mnt/sdb/24_yyx/envs/cutamp-rgbd-20261007` 安装任务已终态complete，原安装/等待进程已退出。实际使用torch2.7.1+cu126、cuTAMP0.0.1、cuRobo0.7.8、NumPy2.4.6、Warp1.12.1。原生类型与一次GPU初始化实际运行通过；这不证明所有后续API兼容。

三份冻结输入均成功构建真实 `cutamp.envs.utils.TAMPEnvironment` / `curobo.geom.types.Cuboid`：1个movable，1809个static（含目标盘），无默认桌面或dummy。CPU过程CUDA未初始化，oracle导入尝试0。

| 输入 | 初始状态结果 | 事实数 |
|---|---|---:|
| 默认未知手状态 | visual_hand_state_unknown | 0 |
| 显式pad模型推断 | 接受 | 6 |
| 推断+hand/grip坐标诊断 | 接受 | 6 |

本地结果：`visual-tamp-problem-20261007/native_cpu_unknown.json`、`native_cpu_pad_inferred.json`、`native_cpu_alignment.json`（目录位于 `D:\大三上\科研`）。

## 首次真实GPU调用

当前代码归档提交f3585fa，两端SHA256 `9da4db76ebf8f70f82def5e47d71537292478c550935b86630a22978ab84cc2c`。GPU诊断启动脚本设置外层300秒上限，tmux `rgbd-gpu-probe-20261007` 已结束。

启动前GPU6显存16MiB、利用率0、无compute进程；核对时间UTC 2026-10-07 09:08:53。输入SHA256 `350d617c979a8dad00d0ae68963dfd091f4100546ec88bffcdb299ee67341d59`，CPU结果SHA256 `01a671e7902793ee313eea863b05398cb0e4fb62fa1ccaab6398493a15487411`。

实际返回：available=true、feasible=false、num_satisfying=0，耗时7.053秒。错误：`Initial state in collision for object 'obj_003' with cost 0.501946210861206`。没有可执行计划或优化解，没有新环境动作，task_success_verified=false。

这证明正式后端已进入原生CUDA运行并触发初始碰撞检查；不代表已完成粒子优化、轨迹规划或恢复。gpu_status=complete仅表示诊断命令正常返回，不能解释为规划成功。

完整本地证据：`D:\大三上\科研\visual-tamp-problem-20261007\native_gpu_result.json`。原生失败返回的diagnostics尚未保留robot_alignment_debug，不能声称已测量8mm工具偏移对应的运行误差。

## 下一步

定位目标碗可见AABB与每个static代理的交叠，以及原生碰撞球和实际可见点的关系，区分掩码/代理扩张、体素离散化和真实观测接触。保留所有障碍及初始碰撞检查，任何接触处理都需要明确局部几何依据。随后继续视觉碗沿抓取约束、工具模型对齐和完整路径规划。

尚无在线容器闭环或同条件A/B/C结果。
