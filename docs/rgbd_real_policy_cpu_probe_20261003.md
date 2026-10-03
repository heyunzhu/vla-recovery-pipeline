# 真实 Pi0 checkpoint 的跨 Python CPU 推理（2026-10-03）

## 本轮结果

已使用真实 `/mnt/sdb/24_yyx/models/pi0_libero_openpi` checkpoint 和 OpenPI `pi0_libero` 配置完成两次离线推理。LIBERO Python 3.8 主进程通过文件桥接调用 OpenPI Python 3.11 worker，后者实际调用 `create_trained_policy` 加载权重并返回动作。这里使用真实策略，区别于前一轮的 fake-policy 传输 smoke。

输入来自此前服务器采集的 task 0 / init 1 / seed 11、静置 10 步后的 512 分辨率同步 agentview 与 robot0_eye_in_hand RGB-D。probe 验证两个相机的 episode、env_step、时间戳、本体状态相同，使用普通 task language 和机器人本体 state；sensor 已将 OpenGL RGB 在 Y 方向翻转，因此再翻转 X，恢复正式 policy runner 的图像输入方向。

probe 不创建仿真环境、没有动作 sink。它只返回动作数组，不测任务成功，不执行恢复。

| 项目 | 第一轮 | 退出修复后复查 |
| --- | --- | --- |
| 真实权重加载 | 成功 | 成功 |
| 动作 shape | 50×7 | 50×7 |
| 动作有限性 | 全部有限 | 全部有限 |
| checkpoint 加载耗时 | 80.17 秒 | 32.64 秒 |
| 单次推理耗时 | 13.38 秒 | 12.12 秒 |
| worker 退出码 | -15 | 0 |
| policy/recovery 动作执行 | 0/0 | 0/0 |
| GPU 使用 | 无 | 无 |

两次输出的动作数组完全相同，输出 NPZ SHA-256 均为 `7f18b829bccd4a6bf0e172d17d95859b4bd81f791ef0892852ff68d266454e9c`。这只验证同一观测的两次实际输出一致，不代表不同任务上的精度或控制稳定性。耗时包含当前缓存/初始化条件，不是吞吐基准。

证据：[第一轮结果](rgbd_real_policy_cpu_probe_report_20261003.json)、[正常退出复查](rgbd_real_policy_cpu_probe_v2_report_20261003.json)。已取回并重新校验输出哈希、shape 与有限性；原始数据和输出数组位于 `D:\大三上\科研\real-policy-cpu-probe-20261003` 与对应 `-v2` 目录。

## 退出修复

第一轮 worker 已写 close 响应，但原桥接仅等待进程退出 2 秒，随后发送 SIGTERM，导致退出码 -15。将已确认 close 后的退出宽限期延长至 15 秒，复查得到退出码 0。未取消启动/推理超时，异常/挂起时仍只清理本 worker 的进程组/进程树。

完整测试 **614 项通过**，包括桥接的正常关闭、错误、启动和推理超时清理测试。复查启动脚本首次因 Windows CRLF 未启动 Python；改为 LF 后重新启动，结果目录由实际成功运行创建，未混用失败脚本的结果。

## 资源与来源

检查时八张 GPU 均有现有任务，因此使用 CPU。通过 `taskset -c 0-7` 将主进程与继承其 affinity 的 worker 限制到 8 个逻辑核；OMP/OpenBLAS/MKL 线程数设为 1。CPU worker 设置 `CUDA_VISIBLE_DEVICES=""`、`JAX_PLATFORMS=cpu`。在个人 tmux 中运行，启动最多 600 秒、推理最多 300 秒。两次检查均已结束，没有遗留模型任务。

| 产物 | 路径 / 哈希 |
| --- | --- |
| 第一轮 runtime | `/mnt/sdb/24_yyx/projects/real-policy-probe-runtime-20261003` |
| 第一轮数据 | `/mnt/sdb/24_yyx/demo/real-policy-cpu-probe-20261003` |
| 第一轮包 SHA-256 | `701748caae73b34e4123486ef88004b99e6ead88c6ae41807950e28c8f9c2489` |
| v2 runtime | `/mnt/sdb/24_yyx/projects/real-policy-probe-runtime-20261003-v2` |
| v2 数据 | `/mnt/sdb/24_yyx/demo/real-policy-cpu-probe-20261003-v2` |
| v2 包 SHA-256 | `e161ba80dd692eb23511ffbfc4d9d57691975b99f5fed83a6d03c39c28501041` |

两轮均上传并核验包及 25 个源码文件；[第一轮源码哈希](rgbd_real_policy_probe_source_sha256_20261003.json)、[v2 源码哈希](rgbd_real_policy_probe_v2_source_sha256_20261003.json)。v2 复用了第一轮已固定的相机输入，结果记录了各输入文件哈希。未修改个人 OpenPI 源码、共享环境或同学 checkout。

## 复现与下一步

使用 v2 runtime、已有 probe_input，在个人环境运行：

```bash
taskset -c 0-7 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
/mnt/sdb/24_yyx/envs/libero-official/bin/python \
  scripts/recovery/skill_pipeline/probe_real_cross_python_policy.py \
  --agent-observation /mnt/sdb/24_yyx/projects/real-policy-probe-runtime-20261003/probe_input/agentview \
  --wrist-observation /mnt/sdb/24_yyx/projects/real-policy-probe-runtime-20261003/probe_input/robot0_eye_in_hand \
  --language-summary /mnt/sdb/24_yyx/projects/real-policy-probe-runtime-20261003/probe_input/summary.json \
  --worker-python /mnt/sdb/24_yyx/envs/openpi-jax/bin/python \
  --checkpoint /mnt/sdb/24_yyx/models/pi0_libero_openpi \
  --out-dir /mnt/sdb/24_yyx/demo/real-policy-cpu-probe-new
```

运行目录为 v2 runtime，输出目录须不存在。输入观测不包含当前环境动作结果；输出动作没有经实际执行或可行性验证。`visual_success_verified=false`，不能据此报告 VLA/RGB-D recovery 成功率。

下一步使用已验证的 CPU worker 在真实 LIBERO 环境运行约 8 步的短程视觉策略诊断：至少两次 policy query、每帧重新检测、记录强制 recovery 的 refusal，并验证策略动作执行后的 RGB-D 重新采集。这一步不必等待空闲 GPU，但仍须限制 CPU 资源；恢复动作继续禁止。
