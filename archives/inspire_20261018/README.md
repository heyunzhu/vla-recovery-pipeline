# 启智研究资产归档 · 2026-10-18

分支：`codex/inspire-archive-20261018`，继承已完成的 [SSH 归档](../ssh_20261018/README.md)。

本批归档进行中：已保存冻结运行包、源码、环境版本与可浏览报告；视觉证据和历史实验记录正在逐包校验、上传。最终清单将在完成后补齐。

- [可浏览的实验报告](reports/)
- [冻结 skill packs](view/packs/)；原始目录对应关系见 [pack_mapping.json](view/packs/pack_mapping.json)
- [逐文件清单](manifests/)、[校验和上传记录](provenance/)

`assets/` 使用 Git LFS 保存实际 gzip tar 分卷。将同一 label 的分卷依次拼接即可恢复；也可使用仓库的 `scripts/archive/restore_ssh_research_assets.py` 校验并安全提取。

原服务器研究文件保持原位；此次操作仅限 `xinghanbo-eval` 和指定项目目录。
