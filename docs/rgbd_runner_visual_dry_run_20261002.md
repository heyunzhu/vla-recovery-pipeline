# 正式 runner 视觉 dry-run 路由（2026-10-02）

## 本轮实现

正式入口 `experiments.robot.libero.skill_pipeline.runner` 新增 `--visual_dry_run` 和 `--task_goal_source language_rgbd`。该模式在 torch 修补、VLA 加载、skill 初始化及策略评测循环之前分派至 live canary，使用共享 visual adapter。

`_parse_episode_task` 新增 language_rgbd 分支：从当前视觉 handoff 返回语言实例绑定；缺 adapter 或 RGB-D 帧即拒绝，不进入 `read_scene`/旧 task parser。`_query_state` 新增显式 `scene_source="rgbd"` 分支：返回视觉快照身份、状态、handoff 和不可规划标志，列出缺失的 body pose、holding、contact、完整碰撞和关节状态。没有生成 `target_xyz`、`goal_xyz` 或 BDDL goal aliases。

混合视觉/真值输入拒绝；language_rgbd 不能在普通 oracle 评测模式中使用。普通策略评测仍需 `--pretrained_path`，visual dry-run 不加载策略，因此无需该参数。当前 dry-run 仅支持 ordinary spatial/object/goal suite 中一个显式 1-based task id 和一个 trial，使用 ordinary task language；不执行 skill，也不接 LIBERO-Pro/generated benchmark。限制在 CLI 验证阶段明确检查，防止误将不支持的配置路由到 oracle。

## 服务器实测

已从正式 runner 命令完成一轮 task 0/init 1/seed 11、512、静置 10 步 canary。仿真保持当前帧，本地冻结模型处理专属 RGB-D，服务器接收 artifact 后，回调实际调用 `_parse_episode_task` 和 `_query_state` 的视觉分支，再验证与 adapter perceiver/executor 接口共享 handoff，并拒绝动作请求。

| 项目 | 实际结果 |
| --- | --- |
| 启动入口 | `skill_pipeline.runner` |
| runner 状态查询已路由 | `runner_query_state_routed=true` |
| task binding / query / adapter 读取 | 同一 handoff 与 binding |
| 视觉结果 | `visual_id_candidate`，target `obj_002`、goal `obj_003` |
| provider detector 调用数 | 1 |
| 动作请求 | 拒绝 |
| 命名 oracle 模块导入尝试 | 0 |
| policy / recovery 动作 | 0 / 0 |
| 检测等待期间环境推进 | 否 |
| VLA 策略评测循环接入 | `policy_evaluation_loop_integrated=false` |
| 完整生产 recovery 链接入 | `production_runner_integrated=false` |

证据见 [实际 runner 结果](rgbd_runner_dry_run_report_20261002.json)。这里已接入正式入口及 task/query 函数的诊断路由；旧 `CuTAMPV2OraclePerceiver` 和 `LiberoRobotClient.get_scene` 尚未替换，正常 VLA/recovery 循环也没有消费新视觉 qstate。不能把这次 canary 称为完成 RGB-D recovery。

Guard 的范围继续是三个命名 oracle 模块的导入，不能解释为全进程任意 MuJoCo 内存访问的完整审计。sensor 所用相机标定/深度转换/时钟及白名单本体观测仍合法。详见 [前一轮 live adapter 检查范围](rgbd_live_dry_run_20261002.md)。

## 复现命令

在已配置个人 LIBERO 环境、包含新代码的仓库目录中运行：

```bash
LIBERO_CONFIG_PATH=/mnt/sdb/24_yyx/config/libero \
PYTHONPATH=/mnt/sdb/24_yyx/projects/LIBERO-f78abd68ee283de9f9be3c8f7e2a9ad60246e95c:/mnt/sdb/24_yyx/projects/runner-visual-dry-run-runtime-20261002 \
/mnt/sdb/24_yyx/envs/libero-official/bin/python -u \
  -m experiments.robot.libero.skill_pipeline.runner \
  --visual_dry_run --task_goal_source language_rgbd \
  --task_suite_name libero_spatial --task_ids 1 --episode_index_start 1 --seed 11 \
  --visual_resolution 512 --num_steps_wait 10 \
  --visual_prompts_json frozen_prompts.json \
  --visual_output_dir /mnt/sdb/24_yyx/demo/runner-visual-dry-run-replay-new
```

`task_ids=1` 为首个任务的 1-based ID；`episode_index_start=1` 在本 canary 中作为 init index，seed 依旧按 runner 的 episode seed 规则计算。输出目录须未存在。打印 `VISUAL_FRAME_READY` 后保持该进程，按上一轮 workflow 把当前 observation 交给冻结模型，完整上传 detector artifact，最后写 READY。回传结果验证帧身份、RGB 哈希、配置和 detector ID；不能直接复用其他 episode 的检测 metadata。

## 产物与测试

本次服务器 runtime：`/mnt/sdb/24_yyx/projects/runner-visual-dry-run-runtime-20261002`；结果：`/mnt/sdb/24_yyx/demo/runner-visual-dry-run-20261002`；本地同名结果目录在 `D:\大三上\科研`。

源码包 `runner_visual_dry_run_runtime_20261002.zip` SHA-256：`1dde15899e6751f06e5ad543fb84d010a0962c8b6d92ee236b5cbd7884ea906d`。上传/解包时核验包与逐文件哈希，见 [源码清单](rgbd_runner_dry_run_source_sha256_20261002.json)。仅使用个人新目录，未修改共享环境或同学 checkout。

完整 skill-pipeline 测试 **594 项通过**。新增检查覆盖：main 在 policy/torch 前分派、视觉 task/query 不访问 env、输入缺失或混合不回退、单任务/语言来源配置门槛，以及 language_rgbd 无 dry-run 时提前拒绝。既有 oracle 与任务语言测试继续通过。

## 下一步

为原 perceiver/executor 提供明确版本的视觉诊断适配入口，统一接收本 handoff，并对无法满足的 SceneState/holding/碰撞字段返回类型化拒绝。补这些入口的集成检查后，才逐步让策略评测循环消费视觉状态。当前颜色属性、目标几何与抓取、支撑/净空、持物和成功验收仍未闭合；尚无可执行 RGB-D recovery 成功率。
