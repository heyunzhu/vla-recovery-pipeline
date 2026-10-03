# 跨 Python 策略桥接（2026-10-03）

## 当前进展

新增 `CrossPythonPolicyAdapter` 与独立 `cross_python_policy_worker.py`，正式视觉策略分支可通过 `--visual_policy_python` 指定 OpenPI 的 Python。LIBERO 主进程继续使用自己的环境，worker 只导入 NumPy/OpenPI，不导入 LIBERO、视觉 scene 或 MuJoCo。无需修改全局环境或强行合并依赖。

传输使用个人输出目录内的独立 UUID session：JSON 控制命令与无 pickle 的 NPZ 数组。仅传递两张 uint8 RGB、本体 state（8 维）和语言 prompt；回传 actions 与可选 actions_log_var。请求/响应按递增序号对应，JSON 原子发布，数组先写完再发布就绪响应。动作必须是有限的非空 `[N,7]`。

模型启动和推理分别有超时。失败、进程退出、异常响应、无效动作会停止 worker 并向主进程抛错，不回退 oracle 或假动作。正常关闭发送 close；异常关闭仅清理本次 worker 进程组/进程树。Windows venv launcher 的子解释器与延迟日志句柄释放也已处理。session 与日志保留，便于排查；每次运行写入新的个人 session 目录。

## GPU 设置

跨 Python worker 默认使用 CPU：`CUDA_VISIBLE_DEVICES=""`、`JAX_PLATFORMS=cpu`。使用 GPU 必须显式指定 `--visual_policy_gpu <index>`，且必须同时指定跨 Python worker 路径。worker 禁止 JAX 启动时预分配整张显存；这不代表可以使用别人正在运行的卡，真实实验前仍需查看卡的使用情况。

`--visual_policy_python` 与 `--policy_in_process` 互斥。没有指定跨 Python 路径时，既有同解释器 policy adapter 保留原行为。跨 Python 路径只用于独立视觉策略诊断评测分支，不改变旧 oracle runner 的调用。

## 服务器实际传输测试

已在个人服务器目录运行传输 smoke：

| 项目 | 实测 |
| --- | --- |
| 主进程 | LIBERO 环境 Python 3.8.20 |
| worker | OpenPI 环境 Python 3.11.16 |
| reset / infer / close | 成功 |
| 图像、状态、语言 roundtrip | 成功 |
| actions / logvar shape | 2×7 / 2×7 |
| worker 退出码 | 0 |
| worker GPU 可见性 | 空 |
| 加载策略权重 | 否 |
| GPU 任务启动 | 0 |

使用可确定输出的 fake policy，将输入图像、状态和 prompt 的值编码进返回动作，以确认两端数据一致。这里只证明真实跨版本进程传输与清理，不证明 checkpoint 能成功加载，也不是 VLA rollout。报告：[服务器结果](rgbd_cross_python_transport_report_20261003.json)。

本轮完整 unittest **614 项通过**。新增六项真实子进程测试覆盖：roundtrip/正常关闭、非法输入不消耗序号、worker 错误停止、推理超时停止、非有限输出拒绝、启动超时清理。加上此前的视觉循环测试，共同验证诊断分支的控制流。

## 部署记录

- 个人服务器 runtime：`/mnt/sdb/24_yyx/projects/cross-python-runtime-20261003`
- 传输测试输出：`/mnt/sdb/24_yyx/demo/cross-python-transport-20261003`
- 本地源码包：`D:\大三上\科研\cross_python_runtime_20261003.zip`
- 包 SHA-256：`81fd49d45f4bd728c0b06587c783f7ee860dd832aa54f483414a6987acd40ad5`

上传后核验包与 24 个源码文件，[源码哈希清单](rgbd_cross_python_source_sha256_20261003.json)。没有修改共享 Python 环境或同学 checkout，传输测试 worker 已退出。

复现传输测试（新输出目录）：

```bash
cd /mnt/sdb/24_yyx/projects/cross-python-runtime-20261003
/mnt/sdb/24_yyx/envs/libero-official/bin/python \
  scripts/recovery/skill_pipeline/smoke_cross_python_policy.py \
  --worker-python /mnt/sdb/24_yyx/envs/openpi-jax/bin/python \
  --out-dir /mnt/sdb/24_yyx/demo/cross-python-transport-new
```

## 真实策略配置与剩余验证

在上一轮视觉策略评测命令基础上增加：

```bash
--visual_policy_python /mnt/sdb/24_yyx/envs/openpi-jax/bin/python \
--visual_policy_startup_timeout_s 600 \
--visual_policy_infer_timeout_s 120
```

worker 会在指定的 OpenPI 环境加载 `--config_name` 与 `--pretrained_path`；选择空闲 GPU 后才添加 `--visual_policy_gpu <index>`。不指定该选项会使用 CPU，可能很慢。

检查时服务器八张 GPU 仍均有任务占用，本轮没有启动真实权重任务。下一步需要验证 OpenPI worker 的 checkpoint 加载与真实 infer，再执行 8 步左右、多 query 的视觉策略 rollout。逐帧冻结 detector 的交接仍需完成；视觉 grasp/支撑/持物/成功验收未闭合，恢复动作仍禁止。
