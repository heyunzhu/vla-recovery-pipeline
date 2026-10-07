# 原生视觉世界验证准备

2026-10-07。正式世界转换已提交 c700719，本次继续补实际原生运行入口。

`probe_native_visual_world.py` 在 CUDA_VISIBLE_DEVICES 为空的进程中加载实际 problem.json，经序列化往返检查构建原生 cuTAMP TAMPEnvironment 和 cuRobo Cuboid，并检查目标盘碰撞保留、显式初始状态及 oracle 导入拦截计数。输出实际依赖版本和类型。该命令不调用求解器，不执行环境动作，也不添加 HandEmpty。

`run_native_visual_world_after_setup.sh` 只跟随已有个人安装进程，在安装成功后启动 CPU 世界检查。等待时同时检查真实安装进程句柄；失败或进程丢失会退出并留下日志，不会重启安装。CPU 检查成功也仅能证明 API/世界构建，不代表 GPU 规划或恢复成功。

视觉后端子进程强制关闭继承的 CUTAMP_CONTACT_MODE_TARGET、CUTAMP_ALLOW_START_COLLISION_ESCAPE 和 CUTAMP_START_ESCAPE_Z。当前官方 cuTAMP 源码未发现这些变量的消费点；此改动也覆盖将来运行带扩展的后端时的继承风险，不据此声称已修复原生碰撞算法。

7 项场景转换针对性测试通过，包括序列化往返和继承环境变量覆盖。上轮完整测试为780项，本次未重复完整测试；原生检查尚待安装完成。

## 已部署的任务

提交：d5b4a8f。代码归档两端 SHA256 均为 `833fc159f3f7a9b26558fa1a171df7ccc85d627771f0e3cd6119867f77348c47`。

个人目录：`/mnt/sdb/24_yyx/setup/native-visual-world-20261007`。tmux `rgbd-native-world-20261007`，启动后真实 bash PID 259710，状态 `waiting existing_installer`。结果将写到 `result.json`，日志为 `probe.log`，终态为 `status.txt`。截至部署时结果尚未生成。
