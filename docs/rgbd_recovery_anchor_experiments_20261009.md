# RGB-D recovery：成功锚点与分阶段对照

2026-10-09，仅操作启智“可上网GPU资源”的 `xinghanbo-eval`。

## 实验边界

锚点为 `libero_goal_task` task04，`Put the wine bottle on the plate`，episode 0、seed 1、init_state_idx 0、base seed 90。沿用历史冻结 runtime、C4 技能包、Pi0 权重及 cuTAMP/执行配置；未强制触发 recovery。具体历史证据见 `oracle_recovery_anchor_wine_plate_20261009.md`。

服务器日志根目录：
`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/`。

## 1. 成功真值 recovery + 同步 RGB-D

目录 `oracle_anchor_rgbd_capture_20261009`。深度渲染开启，分别在恢复入口及入口抬升后、oracle perceiver 求解输入时保存两路相机。传感器输入只包含 RGB、光学 Z 深度、标定及白名单本体状态；物理状态哈希仅用于检查采集是否扰动仿真，不进入视觉输入。

| 检查 | 结果 |
|---|---|
| episode success | true |
| recovery 次数 | 1 |
| 入口控制步 / 时间 | 35 / 1.75 秒 |
| 求解前控制步 / 时间 | 41 / 2.05 秒 |
| 入口抬升推进 | 6 步 |
| 相机 | agentview、robot0_eye_in_hand，各256×256 |
| 两次采集前后物理状态 | 哈希相同 |
| cuTAMP | feasible=true，14个满足候选 |
| 后端耗时 | 64.027 秒，含整体后端调用 |
| 可执行计划 | 存在 |
| 实际 Place 执行 | success=true、done=true，45步 |
| 退出码 | 0 |

局部 `place_drop` 出现 `trajectory_tracking_stalled`，后续 release check 通过、开爪、最终 Place done=true。没有把每条子事件都描述为成功。轨迹随机性存在：本次 Pick 两段63/8步，与前一次30/7步不同。

本地完整采集与验证：`analysis_outputs/oracle_anchor_rgbd_20261009/`，含 `run`、`cutamp_debug`、`snapshots`、`repro_bundle`、`verification.json`。大型产物由 Git 忽略。

## 2. 离线视觉检查

固定 Grounding DINO tiny + SAM2.1 tiny 权重 SHA256，joint detection，box threshold=0.25。只用任务语言产生 bottle=`wine bottle`、plate=`plate`，不读取 simulator 实例名。

先查看四张 RGB，为酒瓶/盘子各标一个内部像素，并标碗/炉灶不应成为 plate 的负例；随后才读取模型结果。标注绑定 RGB SHA256。该验收是像素覆盖及独立实例检查，不是完整 mask IoU、类别数据集准确率或任务成功率。

原配置在四帧均拒绝绑定，原因 `goal_ambiguous`。主视角检测出的三个 plate 分别对应真实盘子、金属碗及炉灶，并非重复框。求解前碗的 plate score=0.432，真盘子=0.365，炉灶=0.270；选最高分会选错。

| 视觉配置 | 入口主视角 | 求解前主视角 | 两张腕部视角 |
|---|---|---|---|
| 任务两类，text=0.25 | 失败，plate歧义 | 失败，plate歧义 | 失败 |
| 补充常见干扰类别，text=0.25 | 失败，盘子未被接受 | 标注检查通过，唯一候选 | 失败 |
| 同一干扰类别，text=0.35 | 标注检查通过，唯一候选 | 标注检查通过，唯一候选 | 失败 |

干扰 prompt 固定为 bowl、stove、cabinet、wine rack、carton，是显式场景词汇，不从本例的 BDDL/真值名单生成。这项配置是看过该锚点后做的调试，不能称为泛化验证。干扰类别仍有误检，例如柜体标为 carton。

另一个确定的接口问题是 `plate bowl` 这类联合 text label：当前代码仅接受与 prompt 完全相同的字符串，混合标签会被直接丢弃。入口帧在 text=0.25 时真盘子因此丢失；升到0.35后得到独立 plate 标签。阈值并未从根本上解决分类证据的表示问题。

`wine bottle` 被现有规则当作未验证 descriptor，因此 binding 状态仍为 `candidate_requires_attribute_check`。本次 RGB 人工检查支持锚点中的候选身份，但没有新增自动属性验证器，也没有把诊断候选升级为正式视觉执行许可。

语言解析补充了 `Put/Place the X on/in the Y`，保留原任务句子；相关语言/绑定检查9项通过。未改动冻结真值 runtime。

## 3. 视觉选择 + 真值几何隔离

目录 `hybrid_visual_selection_oracle_geometry_20261009`。真实求解前重新采图，在隔离进程中使用主视角、干扰词汇、text=0.35检测和绑定。视觉进程没有 simulator 接口。先得到视觉 target/goal ID，再用可见中心的 XY 距离关联 oracle body，距离≤8厘米、最近候选优势≥3厘米，并记录完整关联证据。

这项关联明确使用真值，故属于混合诊断。几何、初始事实、技能触发、抓取/放置配置、执行器及成功判据保留真值基线。BDDL 中原有目标被视觉提名后的关联结果替换；不以 BDDL 目标来选择视觉 ID。`wine bottle` 的身份仅在此锚点经过人工 RGB 检查，未自动解决属性验证。

前一步的实际结果是**完整成功**：本次求解前的新画面检测到5个候选，视觉选择 `obj_001` 酒瓶、`obj_005` 盘子，关联到 `wine_bottle_1_main`、`plate_1_main`，XY距离分别4.42毫米、1.80毫米。检测 artifact 与本次采集 RGB SHA256 一致。

cuTAMP feasible=true，18个满足候选，整体后端38.105秒，有可执行计划。Pick 两段46/7步，闭爪34步，Place46步且 success=true、done=true；episode success=true、recovery_calls=1、abort=false、退出码0。与采集版真值 baseline 的后端配置逐项对照，只有 debug_dir 不同。校验保存于 `hybrid/verification.json`。

这证明本例在调试后的视觉提名下能接回成功执行链；不证明原始检测器或纯 RGB-D recovery 已成功。

## 4. 视觉几何准备与形状诊断

在求解前主视角的通过候选上调用现有 visual adapter，不修改规划/执行权限。

原始酒瓶掩码367个深度点得到包围盒尺寸约 `[0.3046, 0.0486, 0.1574]` 米；成功 oracle 几何约 `[0.0426, 0.0442, 0.1569]` 米。原始边缘深度导致 proxy 中心也偏移。

仅作为离线诊断，将 mask 腐蚀1像素后剩263个点，尺寸变成 `[0.0181, 0.0360, 0.1508]` 米。5%—95%分位范围为 `[0.0562, 0.0374, 0.1476]` 米。巨大变化支持边界背景混入；腐蚀后的可见宽度又小于完整瓶身，不能直接作为完整碰撞尺寸。

当前原样 adapter 产生1个 movable、1个 surface、1727个 static（含未标注深度体素），`solver_initial_state_ready=false`。初始持物状态未知、完整物体体积未知、机器人像素与障碍像素未可靠分开等问题仍在。这不是一次完整 RGB-D recovery 成功运行。

在**本次混合运行的新画面**上又做了原生 cuTAMP GPU 初始碰撞检查，产生1个 movable、1个 surface、1718个 static。酒瓶 AABB 与碗 AABB 在三轴分别重叠约13.0、33.9、50.3毫米；50个目标碰撞球的 full_world_cost=0.122778。该指标是后端碰撞代价，不能直接换算为厘米或成功率。实验只构建世界和检查碰撞，`solver_called=false`、`environment_actions=0`；没有绕过缺失的持物状态去执行完整视觉方案。

结果保存在 `hybrid/visual_geometry_diagnostic/`。检查复用现有 `run_exact_box_task.py`，其 grasp sampler 配置为 `cutamp_native`；本次只测静态碰撞，不将它与完整成功的 `libero_topdown` recovery 求解作同配置成功率对照。

另用同一 cuTAMP 碰撞检查代码分别加载成功的 oracle problem 与视觉 problem，oracle 初始目标碰撞代价为0，视觉为0.099885。两次视觉检查数值略有变化，均为正；这是几何表示造成初始冲突的诊断证据，不是完整规划失败率。复现时过滤了旧 config 中空的 `articulation_options={}` 字段以适配当前后端，未忽略任何非空配置。脚本和结果保存于 `hybrid/collision_check/`。

后续优先修复联合类别标签的静默丢弃和干扰类别分类；清理掩码边界的深度不连续点，并通过多视角或已验证形状先验补足体积；区分支撑面、凹腔、物体、机器人与背景的几何表达；明确空手/持物状态。再在同一成功锚点逐项替换几何、初始状态和执行后的视觉验证，随后扩展到新 seed/任务。分位裁剪和1像素腐蚀只能作为诊断，不能视为完整碰撞保证。

## 本次代码与复现入口

- `scripts/recovery/skill_pipeline/capture_oracle_recovery_rgbd.py`：冻结入口的非推进式采集包装器。
- `scripts/recovery/skill_pipeline/inspect_recovery_rgbd_capture.py`：离线检测、分割、绑定、叠加图，支持显式干扰类别、阈值、相机及阶段选择。
- `scripts/recovery/skill_pipeline/visual_selection_oracle_geometry_hook.py`：明确标记使用真值几何和关联的锚点诊断。
- `experiments/robot/libero/skill_pipeline/visual_language_prompts.py`：直接放置句式支持。

原有未提交修改未覆盖；实验在独立目录进行，未修改/启动其他实例。
