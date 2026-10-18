# 待完成：historical-records

平台在 2026-10-19 01:14 左右自动回收 `xinghanbo-eval`，最后一组旧实验记录的打包尚未完成。其他 66 组已推送；本组的中断分卷不是有效备份，不能据此删除原 NAS 数据。

原实例已请求启动，当前仍在资源队列中。没有创建其他实例；临时 CPU 读取同一项目目录的例外仍待用户允许。

恢复实例后，先检查归档产物目录 `logs/github_inspire_archive_20261018` 的 `historical-records.manifest.json` 与 `archive_finished.json`。若已完成打包，可继续审计/校验；若只有中断分卷，保留它们后重新生成本组。

已写好的 [恢复脚本](provenance/collection_tools/resume_history_after_recycle.py) 只移动本次生成的中断分卷，随后运行服务器已有的 `history_finisher.py`。在确认旧归档进程已随回收结束、没有同组新进程运行后再执行一次，避免重复并发。

本地 `analysis_outputs/inspire_archive_20261018/transfer.py` 可从已保存状态继续上传。完成后运行清单引用检查、远端检查、总索引生成和固定 SHA 的 Git 推送。具体脚本副本保存在 `provenance/collection_tools`，其中平台路径及本地工作区路径需按实际环境映射。
