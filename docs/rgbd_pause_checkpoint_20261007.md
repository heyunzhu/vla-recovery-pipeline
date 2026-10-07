# 暂停检查点（2026-10-07）

用户要求先暂停并保存进度。迁移目标未完成，恢复后从此检查点继续。

## 已验证的状态

- 分支 feature/rgbd-recovery，暂停前最后完成提交 d1dcc23。
- 个人服务器 cuTAMP/cuRobo 安装已完成；原安装和CPU等待任务已结束。
- 三份CPU视觉输入成功构建实际原生世界：1个movable、1809个static。未知手状态拒绝，显式pad模型推断接受6个初始事实。
- 首次GPU6规划调用正常返回但不可行：目标碗obj_003初始碰撞，cost 0.501946210861206，耗时7.053秒。该GPU诊断任务已结束，无新环境动作。
- 最近完整测试为789项通过；其后GPU入口等10项相关测试通过。下面的碰撞归因草稿尚未测试。
- 未完成正式可执行轨迹、视觉持物验证、工具模型对齐、在线恢复闭环、容器任务及同条件A/B/C验收。

## 本轮发现与未验证草稿

CPU检查发现目标碗AABB与49个static代理交叠：目标盘、ramekin和47个体素。该结果是代理交叠，不能直接解释为物理碰撞。

新增草稿文件已保存：

- `experiments/robot/libero/skill_pipeline/visual_proxy_overlap.py`：显式cuboid距离、球/盒交叠及可见点归因。
- `scripts/recovery/skill_pipeline/probe_native_initial_collision.py`：拟保存实际原生碰撞球，分别检查单障碍代价和完整世界代价，同时取得机器人坐标诊断。

这两份草稿未测试、未部署、未运行。恢复时先修正已发现的API调用：固定cuTAMP的 `pose_list_to_mat4x4(pose)` 只接受一个参数，草稿当前额外传了tensor_args；应修正并核对返回tensor的设备后再运行。

## 产物位置

本地 `D:\大三上\科研\visual-tamp-problem-20261007`：problem.json、problem_pad_inferred_v2.json、problem_pad_alignment_v3.json、native_cpu_unknown.json、native_cpu_pad_inferred.json、native_cpu_alignment.json、native_gpu_result.json，以及代码归档和夹持间隙诊断。

服务器 `/mnt/sdb/24_yyx/setup/native-visual-world-gpu-20261007`：runtime、problem.json、result.json、gpu_result.json、gpu_probe.log、gpu_status.txt。gpu_status=complete只表示诊断结束，规划结果feasible=false。

## 恢复顺序

1. 核对当前代码、草稿API和产物摘要，补必要的几何距离测试。
2. 重新检查服务器GPU占用，在空闲卡上运行有时限的归因诊断；此前GPU6空闲不能代替新的检查。
3. 区分AABB虚构表面、体素扩张、掩码边界与实际可见几何交叠，再改善碰撞表示。保留初始碰撞检查。
4. 继续视觉碗沿抓取接入、原生工具模型对齐和正式规划/执行闭环，最终按迁移报告完成对照验收。

暂停时未启动新的后台实验；无需继续安装或重复首次GPU调用。
