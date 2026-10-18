# 启智平台与资产合同

## 平台与固定实例

- 项目：具身智能助行外骨骼关键技术研发。
- 用户指定空间：可上网GPU资源。
- 本研究评测仅操作交互式建模实例 `xinghanbo-eval`，不得操作其他实例。
- 沿用镜像：`ngc-cuda:12.4.1-devel-ubuntu22.04`。
- 默认存储池：hdd。

## Canonical Remote Paths

根目录：`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo`。

- Python：`envs/rlinf-openpi/bin/python`。
- 策略模型：`models/pi0_libero_openpi`。
- LIBERO-PRO：`third_party/LIBERO-PRO`。
- 冻结 Core-60 运行包：`logs/continual_skill_core60_pilot_20261006`。
- 冻结运行代码：该运行包的 `runtime_repo`，commit `7128c1ea6280c227e48561e621fe9da8604c5a6d`；运行时仍须核验。
- C4 pack：该运行包的 `checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918`。
- 历史 object 受控扰动：`logs/pro_object_batch_20261004_mrs200`。

## 同步与保护

历史 benchmark 使用冻结运行实现，不混入本地 RGB-D 迁移分支。新实验写入独立目录，保留命令、源码哈希、pack 哈希、任务和初始化 manifest。不得覆盖源 BDDL、初始化、模型或历史日志。

不在本文件记录凭据、连接地址、实时运行状态。资源状态和确切资产存在性必须每次实时核验。
