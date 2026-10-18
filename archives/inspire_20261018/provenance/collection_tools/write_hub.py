from pathlib import Path
import json,subprocess
r=Path('E:/VLA_recovery_workspace/vla-recovery-ssh-archive');a=r/'archives';ssh=json.loads((a/'ssh_20261018/archive_index.json').read_text(encoding='utf-8'));ins=json.loads((a/'inspire_20261018/archive_index.json').read_text(encoding='utf-8'))
files=json.loads(subprocess.check_output(['git','lfs','ls-files','--json'],cwd=r,text=True))['files'];objects={x['oid']:x['size'] for x in files}
notice=('**启智归档进行中：已完成 '+str(ins['archive_groups'])+'/'+str(ins.get('planned_groups',ins['archive_groups']))+' 组，最后的旧记录尚未完成。详见 [恢复状态](inspire_20261018/RESUME.md)。**' if ins.get('pending_archive_labels') else '**两批选定资产已完成归档。**')
text=f'''# 研究资产迁移索引

归档分支：`codex/inspire-archive-20261018`。本分支同时收录 SSH 训练服务器与启智的选定研究资产。

{notice}

| 来源 | 入口 | 重点内容 | LFS 大小 |
|---|---|---|---:|
| SSH `/mnt/nas/gezuhao/xinghanbo` | [SSH 归档与恢复说明](ssh_20261018/README.md) | 两版最佳 native 检测权重、完整检测数据、自训 uncertainty checkpoint、历史代码/skill/记录 | {ssh['total_lfs_referenced_bytes']/1e9:.3f} GB |
| 启智 `xinghanbo-eval` | [启智归档与恢复说明](inspire_20261018/README.md) | 冻结真值基线、RGB-D 原始证据、实际部署代码、历史 HF8 模型和实验记录 | {ins['unique_new_lfs_object_bytes']/1e9:.3f} GB |

当前分支共引用 **{len(objects)} 个不同 LFS 对象，约 {sum(objects.values())/1e9:.3f} GB**。原服务器研究文件保持原位；两批归档均经过全文件 SHA256 校验，并有 GitHub 对象下载可访问性及长度检查。

先按各批 README 跳过大文件克隆，再按需下载和恢复。环境二进制、全部公共底模、完整 Git 历史、临时压缩包与重复调试数据没有全量保存；确切范围以各批索引和清单为准。

算法实验的工作分支为 `feature/rgbd-recovery`。归档目录另外保存当时实际部署的文件快照；重现特定实验应使用对应冻结代码、配置、skill、任务初始化和模型。
'''
(a/'README.md').write_text(text,encoding='utf-8');print('TOTAL_BRANCH_LFS_OBJECTS',len(objects),'GB',sum(objects.values())/1e9)
