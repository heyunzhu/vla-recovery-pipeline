# 原生 GPU 规划入口与坐标核对准备

日期：2026-10-07。范围：离线、冻结 RGB-D 场景；仍无新环境动作。

新增 `probe_native_visual_planner.py`。运行前核对 CPU 原生世界构建结果与输入文件SHA、同一快照、已接受的初始状态及零oracle导入尝试。禁止oracle初始状态、持物预绑定、轨迹失败后的优化解兜底、起点限位投影和诊断约束放宽。

进程启动前重新读取 nvidia-smi：指定卡须显存≤256MiB、利用率为0、无compute进程。随后只暴露该卡。检查是当时占用观测，不是共享GPU预约；实际运行前还需遵守实验室卡占用规范。

求解预算上限128粒子、60步优化、算法循环30秒，保留原生cuRobo运动规划和轨迹序列化。算法预算不等于进程总时限，部署时还需外层timeout覆盖CUDA加载/编译等阶段。命令只调用规划后端，不包含环境执行器；即使feasible=true也保持execution_allowed=false和task_success_verified=false。

## 坐标诊断

视觉问题新增基座系下的实测grip_site位置、right_hand四元数和实测hand位置。原生后端诊断增加hand位置误差，原有tool位置误差同时保留。

静态源码核对发现：本项目 Panda grip_site 距hand为0.097m，固定官方cuTAMP原生tool偏移为0.105m，相差8mm。该发现是静态模型差异，尚未由实际CUDA FK测出；不能把这一差异记成独立标定成功。规划器的工具/夹爪模型还需对齐，当前未修改原生模型。

新问题文件：`D:\大三上\科研\visual-tamp-problem-20261007\problem_pad_alignment_v3.json`。10项针对性测试通过，包括匹配CPU证据、拒绝旧快照、禁止兜底标志、拒绝GPU占用。此前完整789项测试通过，本次新增入口没有运行GPU，也未重复完整测试。

服务器cuRobo仍在编译，实际nvcc已推进到sphere_obb_kernel.cu；两个CPU原生检查仍跟随安装。GPU运行结果尚不存在。
