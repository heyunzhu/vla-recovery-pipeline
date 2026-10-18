# 两台服务器的研究资产盘点（2026-10-18）

目标：在迁移前明确哪些资产值得优先保存。本次只读检查，没有搬动、删除、清理实验文件，也没有修改全局环境。此文档是盘点，不代表资产已下载或备份完毕。

## 核实范围

| 位置 | 根目录 | 本次证据 |
|---|---|---|
| 启智 `xinghanbo-eval` | `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo` | 当天直接读取过 native50、known-model pilot 产物；盘点时实例变为 PENDING，不能完成全盘重新核验或核算大小 |
| SSH 训练服务器（5476） | `/mnt/nas/gezuhao/xinghanbo` | 在线核实目录、两版最佳权重哈希、COCO 标注数量、部分体积、旧仓库状态、自训 checkpoint 文件 |
| 本地/GitHub | 当前仓库 `feature/rgbd-recovery` | `git ls-remote` 核实远端 HEAD 为 `cdb915f50f1c01b8d70c23be9c63ba088ce41f1b`；本地 Git LFS 跟踪 19 类最佳权重 |

SSH 的完整递归扫描遇到 NAS 磁盘等待，已请求停止本次扫描，改用已完成的定点核验。没有将共享 NAS 的容量或其他用户文件计入本项目。文中大小为十进制 GB；`du` 是占用空间，不跟随符号链接，不等于迁移解引用后的传输大小。

## 启智：核心价值在冻结基线和视觉 recovery 原始实验

以下路径相对于启智根目录。历史项的语义来自仓库结果报告与既有读取记录，不能视为本次已重新遍历所有文件。

| 优先级 | 目录/资产 | 保留原因与范围 |
|---|---|---|
| 最高 | `logs/continual_skill_core60_pilot_20261006/` | 全真值路线的冻结 Core-60 对照，报告包含 1800 个有效 ep。应保留 `runtime_repo`、运行 overlay、C0–C4 skill/checkpoint 包、BDDL、初始状态、配置、命令、逐 ep 结果与视频；只带最终成功率表无法复现 |
| 最高 | 上述目录的 `checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918` | 视觉 recovery 沿用的 C4 pack，触发、抓取、grounding、geometry 和放置参数都依赖它；名称叫 checkpoint，但包含 skill 资产，不只是神经网络权重 |
| 最高 | `logs/rgbd_core60_20261017/` | 300 ep 视觉 recovery 基线（本地已保存最终汇总：52 个任务成功）；保留原图、深度、mask、标定、绑定结果、求解输入/输出及逐帧日志，用于后续训练和失败归因 |
| 最高 | `logs/rgbd_native_mmdet_20261018/` | 原生 19 类 DINO 接入后的 50 ep，4 个任务成功；包括实际部署源码、native/HF 差异诊断、两张图 native 一致性证据、检测器配置及完整失败样本。当天已直接读取产物 |
| 最高 | `logs/rgbd_known_model_20261018/` | 最新“固定真实形状 + 视觉估计位姿”实验。已有三种固定模型、6 个离线配准样本与部署代码/哈希。12 个配对 ep 刚启动后实例又进入 PENDING；最后取得进度为 0/12，不应作为已完成结果 |
| 高 | `logs/rgbd_ten_tasks_20261015/` | 多任务视觉失败与真值对照，尤其 `03_goal_cheese_rack/oracle` 成功案例及其原生 cuTAMP 输入/输出 |
| 高 | `logs/rgbd_oracle_comparison_20261017/`、`logs/rgbd_collision_aligned_20261017/` | 已完成目标几何和碰撞规则受控对照，能解释“真值成功、视觉失败”到底来自哪里 |
| 高 | `logs/rgbd_saved_skill_20261017*`、`logs/rgbd_partial_tracking_20261017*`、`logs/rgbd_release_candidate_20261017*`、`logs/rgbd_rack_placement_20261016*` | 启用历史 skill、释放高度、逐帧跟踪和 rack 成功/失败证据；具体目录集合需实例恢复后重新列举，不按通配符盲目删除 |
| 高 | `third_party/LIBERO-PRO/` 及 run-local BDDL/init-state/config | 定制 task/swap/扰动资产与场景初始化，不能假定重新克隆上游就能恢复相同 benchmark |
| 中 | `models/pi0_libero_openpi`、DINO/SAM/BERT 公共底模 | 通常能重新获得，但应记录版本、哈希、norm_stats、tokenizer；定制/修补内容优先于公开大文件 |
| 中 | `envs/rlinf-openpi`、`envs/tiptop-planning-py310`、run-local native 环境及依赖 | 当前环境有工程价值。先保留依赖版本、安装脚本、源码、wheel 和局部修补；直接复制 venv 不保证能跨机器运行 |

启智完整总大小目前未测得。`logs/` 往往还包含冻结代码、模型副本、环境等内容，不能统一按“可丢弃日志”处理。视频与原始深度数据大多不在 Git 中。

## SSH：核心价值在 DINO 数据、自训模型和早期 skill 研究

以下路径相对于 `/mnt/nas/gezuhao/xinghanbo`。

| 优先级 | 资产 | 已核实大小/数量 | 价值 |
|---|---|---:|---|
| 最高 | `datasets/rgbd_dino_full_20261018/` | 2.889 GB；7,412 图、19 类 | 新检测器的正式训练/验证/测试数据。必须带 `images640`、`instance_masks640`、`states`、`annotations`、`taxonomy.json`、`dataset_audit.json` |
| 最高 | `models/rgbd_dino_full_20261018/training/best_coco_bbox_mAP_epoch_10.pth` | 710,647,898 B | 当前实际使用的原生 MMDetection 权重；配套 `config.py`、类别表、校准阈值必带。GitHub 中已用 LFS 跟踪同哈希文件 |
| 最高 | `datasets/rgbd_dino_20261015/` | 0.929 GB；1,500 图、8 类 | 上一轮训练数据与防泄漏对照。包含 256/640 图像、mask、states、split/identity audit，不能仅留 COCO 框 |
| 最高 | `models/rgbd_dino_finetune_20261015/training/best_coco_bbox_mAP_epoch_5.pth` | 693,373,018 B | 旧 8 类最佳模型，后续做消融和回归需要；未在当前仓库发现对应 LFS 文件 |
| 最高 | `logs/rgbd_dino_full_20261018/`、`logs/rgbd_dino_finetune_20261015/` | 体积未完整核算 | 采集记录、源任务/init-state、真实 handoff 分布、训练协议/曲线、原始/旧/新模型评估、HF 导出差异与源码哈希 |
| 最高 | `code_snapshots/rgbd_dino_full_20261018/`、`rgbd_dino_finetune_20261015/`、`rgbd_dino_integration_20261016/`、`mmdetection_rgbd_20261015/` | 已确认存在 | 与具体训练相配套的实际代码，包含自定义数据/查询变换；不能用未来最新代码替代当时源码 |
| 最高 | `checkpoints/openpi_jax_uncertainty/pi0_libero_uncertainty_head_only/pi0_libero_uncertainty_headonly_frombase_1k_offline_20260810/` | 49 个文件，逻辑大小 10.157 GB；step 500/999 各约 5.079 GB | 自训不确定性模型。是完整 Orbax checkpoint 树，不能只复制顶层 metadata；是否与其他服务器有同哈希副本尚未核验 |
| 最高 | `openvla-oft/skill_packs/`、`openvla-oft/skills/`，及旧代码的未提交内容 | 目录已核实 | 历史 skill 挖掘与配置资产。需保留当前工作树及 Git 信息，而非只记 HEAD |
| 高 | `LIBERO-PRO/` 的本地 task/swap/扰动 BDDL 和 init_files | 2 条 tracked 修改、46 条 untracked 状态条目 | 包含 `pro_object_axis_20261003_task`、`pro_object_batch_20261004_task`、`random_axis_20261003_task` 等。untracked 条目可能代表整个目录，不能理解成仅 46 个文件 |
| 高 | 229 个 `logs/` 实验目录 | 已列举，未全部逐个判定结果质量 | 早期 LIBERO90 baseline/regression、跨 suite skill mining、drawer/articulation、grasp/geometry 等研究证据；应先保留 metadata 和代表性成功/失败视频，再考虑缩减重复中间产物 |
| 中 | `models/rgbd_dino_full_20261018/` 整目录 | 7.065 GB | 含最佳权重、epoch 11/12 恢复 checkpoint、初始化权重和导出；需要继续训练时保留 epoch optimizer 状态。19 类 HF 导出未通过一致性，不能当作已验证部署模型 |
| 中 | `models/rgbd_dino_finetune_20261015/` 整目录 | 9.590 GB | 同类训练/导出资产和历史入口对照；可按用途选择保留，暂未删除任何内容 |
| 中 | `models/pi0_libero_openpi/`、`models/RLinf-Pi0-LIBERO-Spatial-Object-Goal-SFT/` | 已列举 | 基础策略和历史弱 RLinf 对照。先保存准确来源、norm_stats、兼容性修补，再决定是否重复搬运公开参数 |
| 中 | `openpi/`、`ASPIRE/`、`third_party/`、`envs/` | 已核实部分 Git 状态/目录 | 上游源码、局部修补、依赖以及 runtime。ASPIRE 还存在 SAM 服务脚本和 contact-graspnet 子模块修改 |
| 待甄别 | 旧 `openvla-oft_*`、`code_bundles/`、`_archive/`、`_upload_tmp/` 等 | 未逐字节去重 | 名称像同步包或副本，但未确认内容相同，不能据名称判定无价值 |

### 数据 split（直接读取 COCO 文件）

| 数据 | train | val | test |
|---|---:|---:|---:|
| 19 类 640 | 4,418 | 1,508 | 1,486 |
| 8 类 640 | 1,000 | 250 | 250 |

19 类标注数量分别 23,646 / 8,049 / 7,947。8 类 640 标注数量分别 3,290 / 870 / 752。不能将双分辨率文件数当成独立样本数。

### 最佳权重 SHA256（本次重新计算）

```text
19-class epoch10  735b0e3ca9f8a44ad97dbaec97d15c61f18248e01d3e1479d0556d50f3388edd
 8-class epoch5   12c97487fc59fcbf1da38b081c941e6024fa4f8af0c02e0e31cbc308c87b96b6
```

### 旧源码状态（直接读取，未写 global safe.directory）

| 目录 | HEAD | 状态 |
|---|---|---|
| `openvla-oft` | `d72f31f4b199285ee2d5eec0d2b1d14fa911af6a` | 716 条 tracked 修改，38 条 untracked 条目；不应假定 HEAD 能恢复当前文件 |
| `openpi` | `c991bcc3ce7096cfeb24654c442103d7e5d4d9c4` | 6 条 untracked，含历史兼容/uncertainty 修改备份 |
| `LIBERO-PRO` | `eafdb809426b13153aa1e4c42d6601844217dfec` | 2 条 tracked 修改，46 条 untracked 条目 |
| `ASPIRE` | `f4c8939aab0af9b97690c561bd80e282940f7886` | 2 条 tracked 修改，1 条 untracked 条目（含子模块状态） |

修改条数是 Git 状态行数，不代表均为独有功能修改；未做语义去重。两个 standalone/smoke 目录的 HEAD 未成功解析，不能标为“已安全入库”。

## 建议迁移顺序

1. **先保住源码和小型复现资产**：当前本地未提交的 known-model 实现及结果文档；两台服务器的独有代码/补丁、skill packs、BDDL、init-state、taxonomy、校准阈值、实际命令、manifest、逐 ep 汇总。GitHub 已有的只是其中一部分。
2. **带走两份正式检测数据 + 两个最佳权重**：约 5.23 GB（数据占用加权重文件字节数的估算），再加配置、评估与采集 manifest。这是体积小、复用价值高的一个完整实验包。
3. **保存自训 uncertainty checkpoint**：先确定 step 999 是否是使用版本；迁移时保留完整 checkpoint 目录和依赖，step 500 是否需要继续留作对照另行判断。
4. **保存启智冻结真值基线与视觉原始证据**：尤其 Core-60、native50、known-model pilot 和对应 skill/runtime。完整视频和深度可分批，但评测定义与源码不能缺。
5. **最后处理可重新获取或明显重复的大文件**：公开底模、下载缓存、重复 venv、重复代码包。需要先比较哈希/来源/依赖，不依据目录名称直接删。

目前没有执行打包、下载、跨服务器同步、提交或清理。SSH 数据盘上的完整模型目录和数据目录合计约 20.47 GB；这不是整个项目的大小，也不包含上述约 10.16 GB uncertainty checkpoint、历史视频和启智数据。

## 证据保存位置

仓库中的 `asset_inventory_20261018_evidence.json` 保存核心核实事实。详细本地只读快照在 `analysis_outputs/asset_inventory_20261018/`：`ssh_details.json`、`ssh_repositories.json`、`ssh_sizes.json`、`inspire_access_status.json`。该目录默认被 Git 忽略，不应把它本身当作已入库备份。
