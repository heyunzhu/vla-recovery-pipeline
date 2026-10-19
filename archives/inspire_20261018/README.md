# 启智研究资产归档 · 2026-10-18

分支：`codex/inspire-archive-20261018`，继承 [SSH 服务器归档](../ssh_20261018/README.md)。来源为用户指定的 `xinghanbo-eval`，根目录 `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo`。归档跨 10 月 18–19 日完成，名称沿用启动日期。

**本批选定资产已全部归档、校验并推送。**

本批保存 **67 组归档**、约 **258,342 个不同源路径**；压缩分卷总计 **13.989 GB**，对应 **109 个不同 LFS 对象 / 13.989 GB**。原研究文件保持原位，未重跑或补齐未完成的实验。

## 主要内容

| 归档 | 保存内容 | 文件数 | 压缩大小 |
|---|---|---:|---:|
| `frozen-baseline` | Core-60 冻结运行代码、五个 skill pack、任务定义与初始状态 | 1,289 | 0.002 GB |
| `inspire-source` | 启智主仓库、旧工作树、规划/仿真依赖与选定静态资产 | 15,685 | 0.594 GB |
| `visual-runtime` | 各轮视觉实验实际部署的代码、运行 overlay、传感器和 native 配置 | 60,122 | 0.833 GB |
| `core60-results` | 冻结 Core-60 的逐 ep 结果、trace、原生求解样例与视频 | 7,667 | 0.430 GB |
| `rgbd_core60_20261017` | 视觉 recovery 实验：配置、逐 ep 结果和筛选后的 RGB-D/几何/视频证据 | 35,623 | 4.496 GB |
| `rgbd_native_mmdet_20261018` | 视觉 recovery 实验：配置、逐 ep 结果和筛选后的 RGB-D/几何/视频证据 | 13,076 | 1.520 GB |
| `rgbd_known_model_20261018` | 视觉 recovery 实验：配置、逐 ep 结果和筛选后的 RGB-D/几何/视频证据 | 1,553 | 0.159 GB |
| `historical-records` | 其他历史实验、eval_runs 和 _eval_archive 的筛选记录 | 70,003 | 2.251 GB |
| `root-scripts-and-roborsi` | 根目录独有脚本/skill 文档及 RoboRSI 代码、补丁和筛选记录 | 1,549 | 0.004 GB |
| `historical-runtime-and-skills` | 较早实验的运行代码、派生 skill/pack 与配置快照 | 12,665 | 0.183 GB |
| `historical-hf8-detector` | 300 ep 视觉基线实际使用的历史 8 类 HF 导出，仅用于复现 | 10 | 0.646 GB |
| `environment-contracts` | 环境版本、.pth、底模结构及归一化统计 | 4 | 0.000 GB |
| `legacy-cutamp` | 2026-09-05 同步前 cuTAMP 备份中选定的源码/配置 | 83 | 0.002 GB |
| `readable-index` | 便于 GitHub 浏览的实验报告与五个 pack 副本 | 1,018 | 0.011 GB |

另外 **53 组**保存早期视觉迁移、抓取/碰撞对齐、架子放置、逐帧跟踪、DINO 消融等实验；完整目录、字节数、视频和传感器文件数量见 [archive_index.json](archive_index.json)。各分卷最多 250,000,000 字节。

## 直接浏览

- [实验报告与顶层命令/配置](reports/)，以及 [冻结 skill packs](view/packs/)；pack 原始目录见 [pack_mapping.json](view/packs/pack_mapping.json)。这些是脱敏后便于浏览的副本，精确归档字节以分卷和清单为准。
- [Core-60 全真值结果](reports/continual_skill_core60_pilot_20261006/final_metrics.json)、[300 ep 视觉基线](reports/rgbd_core60_20261017/batch_results.json)、[50 ep 原生 DINO 实验](reports/rgbd_native_mmdet_20261018/batch_results.json)。
- [形状配准实验进度](reports/rgbd_known_model_20261018/progress.json)：归档时请求 12 个配对 ep，仅完成 2 个；`pipeline_status` 的 running 字样是旧文件状态，不能当作仍在运行或已完成的证据。
- [逐文件清单](manifests/)、[全部归档恢复校验](provenance/archive_verification.json)、[GitHub LFS 远端检查](provenance/remote_lfs_verification.json)、[环境/源码原始盘点](provenance/inventory.json)、[实际收录规则](provenance/archive_plan.json)。

两个 native 检测权重已在本分支祖先提交中：[19 类模型](../../models/rgbd_dino_full_20261018/) 与 [8 类模型](../../models/rgbd_dino_finetune_20261015/)，没有在启智归档中重复打包。19 类 HF 导出仍不作为可用模型。`historical-hf8-detector` 额外保留 300 ep 基线实际使用的 8 类 HF 导出，用于精确重现历史输入，不表示重新通过了 native/HF 一致性验收。

## 下载与恢复

以下命令在 Linux/macOS shell 执行；先跳过大文件下载，再按需拉取一组：

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --single-branch --branch codex/inspire-archive-20261018 https://github.com/heyunzhu/vla-recovery-pipeline.git
cd vla-recovery-pipeline
git lfs pull --include='archives/inspire_20261018/assets/frozen-baseline.tar.gz.part*'
python scripts/archive/restore_ssh_research_assets.py --archive archives/inspire_20261018 --label frozen-baseline --extract /new/project
```

恢复其他组时同时替换 include 和 label。工具虽沿用 `ssh` 文件名，也支持本目录；它校验每个分卷和每个文件的 SHA256，拒绝覆盖已有文件、符号链接或危险路径。去掉 `--extract` 只做完整内容校验。多组可能包含同一路径的副本，见 [同路径清单](provenance/overlapping_paths.json)。全量恢复时可先把各组分别提取到空目录，再核对清单 SHA256 后合并；工具不会覆盖已有文件。大多数归档路径相对原项目根目录；`readable-index` 恢复的是本页 `reports/`、`view/` 等浏览副本。

例如原生 DINO 复现需要 `frozen-baseline`、`inspire-source`、`visual-runtime`、`environment-contracts` 和 `rgbd_native_mmdet_20261018`，并单独拉取 19 类权重。还需自行准备相同策略底模、创建项目内环境，按环境合同和原命令调整根路径；归档本身不等于已安装可运行环境。

## 范围与限制

最终检查补充了 [大文本完整脱敏审计](provenance/large_text_audit.json)：历史包中 10 个超过原 32 MiB 上限的 JSON 均执行完整扫描，并按 SHA256 确认与归档内文件一致。

- 冻结基线保存实际 runtime、五个 pack、BDDL/init 文件。`core60-results` 保留筛选范围内全部视频、逐 ep 结果和 trace，省去与视频重复的普通帧、原始恢复快照。未把目录中的旧尝试自动等同于最终有效 ep，统计以 `final_metrics.json` 为准。
- 各视觉组按规则保存 RGB、深度、mask、点云、几何模型、视频和文本证据，省去缓存、运行环境二进制、staging/interrupted/启动部署失败副本；重复代码集中保存在 `visual-runtime`。原生求解仅保存每个 debug 父目录首个可用 problem/result 对，未全量保存重复优化中间文件。
- 其他历史实验保留配置、命令、文档、逐 ep 结果/trace 和浅层图表；每个选定顶层根最多保留前两段按路径排序的视频，这不是成功/失败统计抽样。RoboRSI 补充包保存源码、补丁和筛选文本/图表记录，没有复制其 home、缓存、环境或嵌套成功录像 tar 包。嵌套临时 zip/tar 包不全量收录。
- 源码/静态资产按允许类型且单文件不超过 32 MiB；视觉证据上限 256 MiB，历史记录上限 64 MiB。显式排除及脱敏写入清单；隐式目录/类型筛选见采集脚本。没有保存原仓库完整 Git DAG、venv、系统镜像和下载缓存。
- 策略底模目录（合计约 19.026 GB）仅保存 [文件身份与 SHA256](provenance/base_model_hashes.json)、结构和可取得的配置/归一化统计，没有上传其大权重；后续运行需另行准备相同文件。模型身份清单不表示已备份底模。
- SAM2、原始 DINO、BERT 等公共视觉模型权重未全量打包，需按各轮 `vision_config`、配置和修订信息补齐。明确保留的自训检测权重及历史 HF8 导出见上文。
- 归档组数不是成功实验数；空目录、取消尝试和重试以逐文件清单及实验汇总为准。
- 凭据、私钥、运行时认证端点等未纳入，脱敏只修改归档副本。临时中断的打包分卷保留在启智自建归档目录中，不计作有效备份。
- 这是一份选定研究资产归档，未将共享盘全部内容打包，也未删除或清理原服务器数据。启智与 SSH 两批资产各有索引，可从本分支分别恢复。
