# SSH 服务器研究资产归档 · 2026-10-18

分支：`codex/ssh-archive-20261018`。来源根目录：`/mnt/nas/gezuhao/xinghanbo`。
本目录保存实际文件，包含两版最佳检测模型、两份完整正式检测数据、自训 checkpoint、历史源码/skill 和实验记录。原服务器研究文件保持原位。

## 已保存内容

| 归档 | 内容 | 文件数 | 归档大小 |
|---|---|---:|---:|
| `frozen-runtime-inputs` | 正式采集使用的冻结运行代码、C4 pack、BDDL 与初始状态 | 1,222 | 0.002 GB |
| `planning-dependencies` | cuTAMP/cuROBO 源码、CUDA/C++、配置与静态资产 | 666 | 0.054 GB |
| `source-and-skills` | 历史源码、skill、定制任务/初始化与选定静态资产 | 53,973 | 2.097 GB |
| `experiment-records` | 历史实验配置、命令、逐回合结果、训练/评估记录与部分图像 | 50,931 | 1.015 GB |
| `rgbd_dino_20261015` | 8 类检测数据：1,500 张图，含两种分辨率、mask、状态与划分 | 9,073 | 0.899 GB |
| `rgbd_dino_full_20261018` | 19 类检测数据：7,412 张图，含 mask、状态与 COCO 划分 | 22,242 | 2.811 GB |
| `uncertainty-step500` | 自训不确定性实验 step 500 的完整 Orbax 目录 | 24 | 5.080 GB |
| `uncertainty-step999` | 自训不确定性实验 step 999 的完整 Orbax 目录 | 25 | 5.080 GB |
| `runtime-contract` | 基础策略配置与归一化统计 | 3 | 0.000 GB |
| `source-supplement` | OpenPI 历史兼容/uncertainty 代码备份 | 5 | 0.000 GB |
| `repro-lockfiles` | 依赖锁文件与子模块定义（实际存在项） | 3 | 0.000 GB |
| `representative-videos` | 历史扰动实验的成功/失败视频各一段及 episode 记录 | 5 | 0.000 GB |

归档负载共 **17.038 GB**；加上两个独立 native 检测权重，分支引用的 LFS 数据共 **18.442 GB**。19 类权重已在父提交中，本次没有重复存一份。
这是选定资产的大小，不是整个 NAS 项目的占用空间。各分卷最多 1,000,000,000 字节。

- [可直接浏览的历史 skill packs](view/openvla-oft/skill_packs/) 与 [skills](view/openvla-oft/skills/)。其中 quarantine 是历史隔离资产，不表示当前启用。
- [8 类 native 模型](../../models/rgbd_dino_finetune_20261015/) 与 [19 类 native 模型](../../models/rgbd_dino_full_20261018/)。19 类 HF 导出未通过一致性，未作为可用部署模型保存。
- [机器可读索引](archive_index.json)、[逐文件清单](manifests/)、[本地恢复校验](provenance/local_verification.json)。GitHub 对象可读性与大小检查另见 `provenance/remote_lfs_verification.json`。
- [环境版本与 .pth 引用](provenance/environment_inventory.json)；初始盘点与旧 Git 工作树状态保存在 `provenance/`，它们是迁移前快照，当前收录状态以本索引为准。

`assets/` 中是实际 gzip tar 数据的分卷，使用 Git LFS 保存。`manifests/` 记录每个文件的路径、时间、归档字节数、SHA256、脱敏和排除项。`view/` 便于浏览；需要精确字节时以归档及清单为准。

## 按需恢复

已安装 Git LFS 后，先拉取归档分支；避免初次克隆就下载全部大文件：

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --single-branch --branch codex/ssh-archive-20261018 https://github.com/heyunzhu/vla-recovery-pipeline.git
cd vla-recovery-pipeline
git lfs pull --include='archives/ssh_20261018/assets/source-and-skills.tar.gz.part*'
python scripts/archive/restore_ssh_research_assets.py --archive archives/ssh_20261018 --label source-and-skills --extract /new/project
```

将 label 和 include 中的名称换成表中其他归档即可。去掉 `--extract` 只做全文件校验，不生成第二份数据。工具拒绝覆盖现有文件和提取危险路径。Orbax 必须恢复完整目录，不能只复制 metadata。

模型可单独拉取：`git lfs pull --include='models/rgbd_dino*/*.pth'`。下载后以模型 README 中的 SHA256 核对。

## 范围与限制

- 历史源码按允许的文件类型收录，单个源码/静态资产上限 32 MiB；完整规则及排除项见打包工具和清单。保存的是文件快照，未保存原仓库完整 Git 历史。
- 实验记录按文本/图像类型筛选，单项上限 16 MiB；普通历史大日志没有全量收录，DINO 的主要训练日志按规则保存。视频仅选存上述两例，不是视频全集，也不是统计抽样。
- 账号凭据、私钥、运行时认证端点、下载缓存、venv 二进制和 `.git` 内部文件未纳入。敏感字段在归档副本中脱敏，差异写入清单。误建的反斜杠路径等不可安全恢复项列为排除，源文件保留。
- 公开 Pi0/RLinf/BERT 等底模、失败 HF 权重导出、DINO epoch 11/12 optimizer checkpoint、完整历史视频及两个检测数据集以外的原始 RGB-D 流、任意临时同步包没有全量收录。
- 重建运行环境仍需创建项目内环境，并把配置中的绝对路径映射到新根目录；复制本目录不等于已经安装好运行环境。归档也不代表批准删除原 NAS 目录。
- 本次仅覆盖 SSH 服务器；启智冻结基线和视觉实验属于另一批资产。
