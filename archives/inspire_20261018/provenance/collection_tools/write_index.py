from pathlib import Path
import json,datetime,subprocess,re,sys
from pathlib import PurePosixPath
r=Path('E:/VLA_recovery_workspace/vla-recovery-ssh-archive');a=r/'archives/inspire_20261018'
sys.path.insert(0,str(r/'scripts/archive'))
from package_ssh_research_assets import TEXT
plan=json.loads((a/'provenance/archive_plan.json').read_text(encoding='utf-8'));required={x['label'] for x in plan['jobs']}|{'environment-contracts','legacy-cutamp','readable-index','historical-hf8-detector','historical-runtime-and-skills','root-scripts-and-roborsi'}
planned=set(required)
partial='--partial' in sys.argv
if partial:
 required={x for x in required if (a/'manifests'/(x+'.manifest.json')).exists() and (a/'provenance'/(x+'.verification.json')).exists() and (a/'provenance'/(x+'.upload_receipt.json')).exists()}
else:
 finished=json.loads((a/'provenance/archive_finished.json').read_text(encoding='utf-8'));assert set(finished['completed'])=={x['label'] for x in plan['jobs']}
pending=sorted(planned-required)

roles={'root-scripts-and-roborsi':'根目录独有脚本/skill 文档及 RoboRSI 代码、补丁和筛选记录','historical-runtime-and-skills':'较早实验的运行代码、派生 skill/pack 与配置快照','historical-hf8-detector':'300 ep 视觉基线实际使用的历史 8 类 HF 导出，仅用于复现','frozen-baseline':'Core-60 冻结运行代码、五个 skill pack、任务定义与初始状态','inspire-source':'启智主仓库、旧工作树、规划/仿真依赖与选定静态资产','visual-runtime':'各轮视觉实验实际部署的代码、运行 overlay、传感器和 native 配置','core60-results':'冻结 Core-60 的逐 ep 结果、trace、原生求解样例与视频','historical-records':'其他历史实验、eval_runs 和 _eval_archive 的筛选记录','environment-contracts':'环境版本、.pth、底模结构及归一化统计','legacy-cutamp':'2026-09-05 同步前 cuTAMP 备份中选定的源码/配置','readable-index':'便于 GitHub 浏览的实验报告与五个 pack 副本'}
items=[];objects={};source_paths=set();proofs=[];video_counts={};episodes={};raw_counts={};errors=[];path_versions={}
for label in sorted(required):
 m=json.loads((a/'manifests'/(label+'.manifest.json')).read_text(encoding='utf-8'));v=json.loads((a/'provenance'/(label+'.verification.json')).read_text(encoding='utf-8'));sec=json.loads((a/'provenance'/(label+'.security_audit.json')).read_text(encoding='utf-8'));up=json.loads((a/'provenance'/(label+'.upload_receipt.json')).read_text(encoding='utf-8'))
 assert v['verified'] and v['files']==len(m['files']) and v['archive_bytes']==m['archive_bytes'];assert sec['completed'] and sec['policy_version']==2;assert up['complete'] and all(x['registered'] for x in up['objects'])
 assert {(x['oid'],x['bytes']) for x in up['objects']}=={(x['sha256'],x['bytes']) for x in m['parts']}
 for x in m['parts']:
  assert Path(x['name']).name==x['name'];objects[x['sha256']]=x['bytes']
 for x in m['files']:
  path=x['path'];assert not PurePosixPath(path).is_absolute() and '\\' not in path and '..' not in Path(path).parts
  if label!='readable-index':source_paths.add(path);path_versions.setdefault(path,[]).append(dict(label=label,sha256=x['sha256']))
  if x.get('source_bytes',0)>32*1024**2 and Path(path).suffix.lower() in TEXT:errors.append(dict(label=label,path=path,reason='large text outside original sanitization cap'))
  if any(z in Path(path).parts for z in ['.inspire','.ssh']):errors.append(dict(label=label,path=path,reason='unexpected credential-context directory'))
 video_counts[label]=sum(x['path'].endswith('.mp4') for x in m['files']);episodes[label]=sum(Path(x['path']).name=='episode.json' for x in m['files']);raw_counts[label]={suffix:sum(x['path'].endswith(suffix) for x in m['files']) for suffix in ['.npz','.npy','.png','.jpg']}
 role=roles.get(label,'视觉 recovery 实验：配置、逐 ep 结果和筛选后的 RGB-D/几何/视频证据')
 items.append(dict(label=label,role=role,source_root=m['source_root'],files=len(m['files']),source_bytes=m['source_bytes'],archive_bytes=m['archive_bytes'],parts=m['parts'],excluded_count=len(m['excluded']),redacted_files=sum(x.get('redactions',0)>0 for x in m['files']),mp4_files=video_counts[label],episode_json_files=episodes[label],sensor_files=raw_counts[label],server_sha256_verified=True))
 proofs.append(v)
(a/'provenance/final_content_checks.json').write_text(json.dumps(dict(unexpected_or_unscanned_items=errors),indent=2),encoding='utf-8');assert not errors,errors[:5]
overlaps={p:rows for p,rows in path_versions.items() if len(rows)>1}
conflicts={p:rows for p,rows in overlaps.items() if len({x['sha256'] for x in rows})>1}
(a/'provenance/overlapping_paths.json').write_text(json.dumps(dict(overlapping_paths=overlaps,different_content_paths=conflicts),indent=2),encoding='utf-8')
remote=json.loads((a/'provenance/remote_lfs_verification.json').read_text(encoding='utf-8'));assert {x['oid'] for x in remote['files']}==set(objects);assert all(x['accessible'] and x['total_bytes_match'] for x in remote['files']);assert sum(objects.values())==remote['unique_object_bytes']
index=dict(status='in_progress' if pending else 'complete',pending_archive_labels=pending,planned_groups=len(planned),schema_version=1,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),branch='codex/inspire-archive-20261018',parent_commit='f64dfa7ac18270715a4e86f163cbdefcdc949c42',source_root=plan['source_root'],archives=items,archive_groups=len(items),unique_archived_source_paths=len(source_paths),archive_payload_bytes=sum(x['archive_bytes'] for x in items),unique_new_lfs_objects=len(objects),unique_new_lfs_object_bytes=sum(objects.values()),original_research_files_modified=False,scope='selected Inspire assets, not a whole NAS/container backup',existing_model_refs=[dict(path='models/rgbd_dino_full_20261018/best_coco_bbox_mAP_epoch_10.pth',sha256='735b0e3ca9f8a44ad97dbaec97d15c61f18248e01d3e1479d0556d50f3388edd',bytes=710647898),dict(path='models/rgbd_dino_finetune_20261015/best_coco_bbox_mAP_epoch_5.pth',sha256='12c97487fc59fcbf1da38b081c941e6024fa4f8af0c02e0e31cbc308c87b96b6',bytes=693373018)])
(a/'archive_index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(a/'provenance/archive_verification.json').write_text(json.dumps(dict(verification='Independent complete part and member SHA256 verification on Inspire; readable-index additionally extracted and verified on local Windows.',archives=proofs),indent=2)+'\n',encoding='utf-8')
primary=['frozen-baseline','inspire-source','visual-runtime','core60-results','rgbd_core60_20261017','rgbd_native_mmdet_20261018','rgbd_known_model_20261018','historical-records','root-scripts-and-roborsi','historical-runtime-and-skills','historical-hf8-detector','environment-contracts','legacy-cutamp','readable-index']
table='\n'.join(f"| `{x['label']}` | {x['role']} | {x['files']:,} | {x['archive_bytes']/1e9:.3f} GB |" for name in primary for x in items if x['label']==name)
other=[x for x in items if x['label'] not in primary]
browse=json.loads((a/'provenance/readable_index_local_restore.json').read_text());assert browse['verified']
base=json.loads((a/'provenance/base_model_hashes.json').read_text());assert base['complete'];basebytes=sum(x['bytes'] for x in base['files'])
notice=('**归档进行中：已完成 '+str(len(items))+'/'+str(len(planned))+' 组，尚待 '+', '.join(pending)+'。原实例被平台自动回收，已请求重启；本索引不把待完成项计为已备份。**' if pending else '**本批选定资产已全部归档、校验并推送。**')
readme=f'''# 启智研究资产归档 · 2026-10-18

分支：`codex/inspire-archive-20261018`，继承 [SSH 服务器归档](../ssh_20261018/README.md)。来源为用户指定的 `xinghanbo-eval`，根目录 `{plan['source_root']}`。归档跨 10 月 18–19 日完成，名称沿用启动日期。

{notice}

本批保存 **{len(items)} 组归档**、约 **{len(source_paths):,} 个不同源路径**；压缩分卷总计 **{index['archive_payload_bytes']/1e9:.3f} GB**，对应 **{len(objects)} 个不同 LFS 对象 / {sum(objects.values())/1e9:.3f} GB**。原研究文件保持原位，未重跑或补齐未完成的实验。

## 主要内容

| 归档 | 保存内容 | 文件数 | 压缩大小 |
|---|---|---:|---:|
{table}

另外 **{len(other)} 组**保存早期视觉迁移、抓取/碰撞对齐、架子放置、逐帧跟踪、DINO 消融等实验；完整目录、字节数、视频和传感器文件数量见 [archive_index.json](archive_index.json)。各分卷最多 250,000,000 字节。

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

- 冻结基线保存实际 runtime、五个 pack、BDDL/init 文件。`core60-results` 保留筛选范围内全部视频、逐 ep 结果和 trace，省去与视频重复的普通帧、原始恢复快照。未把目录中的旧尝试自动等同于最终有效 ep，统计以 `final_metrics.json` 为准。
- 各视觉组按规则保存 RGB、深度、mask、点云、几何模型、视频和文本证据，省去缓存、运行环境二进制、staging/interrupted/启动部署失败副本；重复代码集中保存在 `visual-runtime`。原生求解仅保存每个 debug 父目录首个可用 problem/result 对，未全量保存重复优化中间文件。
- 其他历史实验保留配置、命令、文档、逐 ep 结果/trace 和浅层图表；每个选定顶层根最多保留前两段按路径排序的视频，这不是成功/失败统计抽样。RoboRSI 补充包保存源码、补丁和筛选文本/图表记录，没有复制其 home、缓存、环境或嵌套成功录像 tar 包。嵌套临时 zip/tar 包不全量收录。
- 源码/静态资产按允许类型且单文件不超过 32 MiB；视觉证据上限 256 MiB，历史记录上限 64 MiB。显式排除及脱敏写入清单；隐式目录/类型筛选见采集脚本。没有保存原仓库完整 Git DAG、venv、系统镜像和下载缓存。
- 策略底模目录（合计约 {basebytes/1e9:.3f} GB）仅保存 [文件身份与 SHA256](provenance/base_model_hashes.json)、结构和可取得的配置/归一化统计，没有上传其大权重；后续运行需另行准备相同文件。模型身份清单不表示已备份底模。
- SAM2、原始 DINO、BERT 等公共视觉模型权重未全量打包，需按各轮 `vision_config`、配置和修订信息补齐。明确保留的自训检测权重及历史 HF8 导出见上文。
- 归档组数不是成功实验数；空目录、取消尝试和重试以逐文件清单及实验汇总为准。
- 凭据、私钥、运行时认证端点等未纳入，脱敏只修改归档副本。临时中断的打包分卷保留在启智自建归档目录中，不计作有效备份。
- 这是一份选定研究资产归档，未将共享盘全部内容打包，也未删除或清理原服务器数据。启智与 SSH 两批资产各有索引，可从本分支分别恢复。
'''
(a/'README.md').write_text(readme,encoding='utf-8')
if not pending and (a/'RESUME.md').exists():(a/'RESUME.md').write_text('# 已恢复完成\n\n此前平台回收造成的中断已恢复处理，当前全部计划归档均已完成。以 archive_index.json 和 README.md 为准；历史中断与校验记录保存在 provenance/。\n',encoding='utf-8')
for link in re.findall(r'\]\(([^)]+)\)',readme):assert (a/link).exists(),link
print(json.dumps(dict(groups=len(items),unique_source_paths=len(source_paths),unique_lfs_objects=len(objects),GB=sum(objects.values())/1e9)))
