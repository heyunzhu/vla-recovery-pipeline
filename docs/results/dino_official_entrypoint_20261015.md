# Grounding DINO 官方入口一致性检查（2026-10-15）

第一步已完成：九张固定 recovery RGB、每张 full_joint/task_joint 两种查询，完成三套实现的 18 组对照，并修复一个真实的空结果接入缺陷。没有训练、没有改变检测类别或阈值、没有重跑 recovery。

## 结论

1. **我们的 DINO 调用封装没有改变输入和原始预测。** 在 Transformers 5.19.0 下，官方文档的 PIL 图像 + caption 字符串调用，与生产 `_ground_image` 的 NumPy 图像 + 类别列表调用，18/18 组的五个输入张量、原始 logits、pred_boxes 和原始检测列表均完全一致。
2. **依赖版本并非数值等价。** IDEA 原仓库与 Transformers 4.40.2 的 18/18 组检测框数及按序类别文本一致；最大框坐标差 0.002003 像素，最大分数差 0.000411。当前 5.19.0 的部分分数、类别和候选数存在更明显变化，不能当作原仓库的严格数值复现。
3. **原始模型也有关键误检。** 原仓库在 06 的联合查询中把篮子认成 carton（0.477）；在 02 的任务类别查询中把机械臂认成 wine bottle（0.431）。4.40.2 复现相同错误；5.19 也输出同类错误。因此并非修正封装或依赖版本就能解决当前识别质量。
4. **确有一个独立的边界 bug，已在本地修复。** 5.19 在零框时可能返回一个空类别字符串，导致生产过滤器误报数组长度不一致。现在仅对“零框、零分数、单个空文本”返回空检测；有非空标签的错误结构仍报错。7 个相关单测通过，真实 04/task_joint 图像重放通过。

主分支是 `feature/rgbd-recovery`，本轮开始时 HEAD 为 `62e4bc8410bcf1211c8b86dc8263746f2c8a6795`，审计脚本、报告和边界修复尚未提交。冻结服务器 runtime 与历史实验未修改。

## 样本与查询

输入沿用十任务实验中九张实际执行过检测的 recovery 首次求解前 agentview 图像。第 10 个任务停在语言解析，未纳入。没有用仿真真值生成本次预测。

- full_joint：原任务类别加原有干扰类别，顺序不变。
- task_joint：只包含任务语言解析生成的类别。
- 框阈值 0.25、文本阈值 0.35。
- 每张 PNG 校验 SHA256；官方与封装的输入内容相同。
- 框缩放到原始 256×256 图像坐标，比较的是过滤前输出，同时单独检查过滤结果。

## 权重与原仓库核验

原仓库：<https://github.com/IDEA-Research/GroundingDINO>，固定 commit `856dde20aee659246248e20734ef9ba5214f5e44`。使用其 `groundingdino.util.inference.load_image/load_model/predict`，默认 `remove_combined=False`，不改模型算法。CPU 使用原仓库自带的 PyTorch deformable-attention fallback。

HF 权重：`IDEA-Research/grounding-dino-tiny`，固定 revision `a2bb814dd30d776dcf7e30523b00659f4f141c71`，model.safetensors SHA256 为 `1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3`。

Native checkpoint 来自原仓库官方 release 的 `groundingdino_swint_ogc.pth`。具体下载 URL、文件大小与 SHA256 见本地 `models/download_manifest.json` 及摘要 JSON。

按 HF 官方转换脚本做键名和 Q/K/V 拆分对齐，另显式对齐该转换脚本未重命名的 12 个 Swin relative_position_index 确定性缓冲区。**HF 文件中全部 990 个张量逐项完全相同，无缺失、无数值差异。** 该数量包含缓冲区，不等同于 990 个可训练参数。

Native 模型实际加载后再次核验：无 missing keys，938 个共有状态张量均与 checkpoint 一致。仅有原 checkpoint 中的 `label_enc.weight` 和 `bert.embeddings.position_ids` 为 unexpected keys，未把缺失权重随机初始化当作有效对照。

原仓库 BERT 初始化所需文件从同一 checkpoint 提取到实验专用目录；配置只替换 BERT 本地路径。另生成仅含 model 张量的 checkpoint，避免新 PyTorch 默认 weights_only 加载被原文件训练元数据阻止。没有修改权重数值。

## 预处理与版本差异

原仓库与 4.40.2 的输入像素张量逐元素一致。原仓库与 5.19 的文本 token 全部一致，但输入像素张量最大差约 0.017507（标准化后的数值），对应 resize 实现差异。

对全部 18 组另做交叉输入：把 5.19 的像素张量直接送入 Native 模型。主要版本差异仍然存在。例如 01/full_joint 的 wine bottle，原仓库使用自身输入或 HF 输入都约 0.864，5.19 则约 0.714–0.717。因此不能只归因于图片 resize。

另外在 01/02/06 三帧、两类查询上检查了 5.19 文本骨干默认 SDPA 与切换 eager 的输出。切换 eager 没有恢复原仓库结果，反而多组输出为空，**不能作为修复方案**。这只是排除一个简单开关，尚未定位到 5.19 的具体变更行；不能把所有版本差异直接归咎于某个注意力算子。

当前证据支持冻结原仓库/4.40.2 作为后续检测训练与评测的参考基线。不能盲目把整个现有环境降到 4.40.2：当前 SAM2 依赖也在同一视觉模块加载，需要后续明确环境边界。本轮未更改生产依赖版本。

直接替换版本还会改变现有阈值下的候选：01/full_joint 中，盘子框在原仓库分数约 0.346、类别文本为空，5.19 则约 0.362 并输出 plate。因此版本对齐不等于成功率提高，后续需要重新校准并重放已成功案例，不能宣称降级即可修复识别。

## 空结果修复

修复前，04/task_joint 的模型前向和官方原始输出正常，但返回：boxes `(0,4)`、scores `(0,)`、text_labels `['']`。过滤器因长度不一致抛 ValueError。

本地 `_resolve_grounded_boxes` 现在只兼容上述空结果形式，返回三个空列表。没有把非空类别改名、没有创建候选，也没有放宽已有实例过滤。

修复验证：

```powershell
python -m unittest experiments.robot.libero.skill_pipeline.tests.test_grounded_sam2_backend -v
```

7 tests 通过；其中新增回归覆盖真实空标签形式、规范空结果、零框但非空类别仍拒绝。另用同权重和真实 04/task_joint RGB 重放，确认无异常且返回空检测。修复前后源码分别保留并记录哈希，正式 18 组一致性结果来自修复前，不把修复后结果混入原审计。

## 计算环境与实例状态

`xinghanbo-eval` 起初 STOPPED，已按用户指令执行 start；后续多次查询均为 PENDING，未获得运行节点。本轮全部推理因此在隔离的本地 WSL CPU 环境完成，**没有在服务器 GPU 执行**。未操作其他实例，没有改变调度规格、优先级或代理。

- 公共基础：Python 3.12.3，torch 2.7.1+cpu，torchvision 0.22.1+cpu，4 个 CPU 线程。
- Native 与旧 HF：transformers 4.40.2、tokenizers 0.19.1、timm 0.9.16。
- 当前 HF：通过独立目标目录加载 transformers 5.19.0 及其依赖，未覆盖旧环境。
- 环境：`/home/dx/.cache/dino-official-audit-20261015`。
- 本地 CPU 审计不能替代以后对目标 GPU 环境的性能或严格数值复现检查。

## 复现入口

审计目录为仓库下 `analysis_outputs/dino_official_entrypoint_20261015`。它包含官方源码快照、下载 manifest、原始数组、逐帧 JSON、叠图和环境记录。`hf519_cpu`、`native_cpu`、`hf440_cpu` 三个目录均有 completed.json，分别完成 18 组。初期资产准备失败目录保留，不计入有效结果。

下面命令在 WSL 执行，`REPO` 指向本地仓库，不依赖模拟器：

```bash
REPO=/mnt/e/VLA_recovery_workspace/vla-recovery-pipeline
AUDIT="$REPO/analysis_outputs/dino_official_entrypoint_20261015"
PY=/home/dx/.cache/dino-official-audit-20261015/bin/python
MANIFEST="$REPO/analysis_outputs/rgbd_detection_ablation_20261015/evidence/run02/manifest.json"
EVIDENCE="$REPO/analysis_outputs/rgbd_ten_tasks_20261015/evidence"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# 当前 HF 官方调用与封装逐层对照。
PYTHONPATH=/home/dx/.cache/dino-official-audit-20261015/hf519 "$PY" \
  "$REPO/scripts/recovery/skill_pipeline/audit_dino_official_entrypoint.py" \
  --code-root "$REPO" --evidence "$EVIDENCE" --manifest "$MANIFEST" \
  --model "$AUDIT/models/grounding-dino-tiny" --output "$AUDIT/hf519_cpu" --device cpu

# 原仓库入口；本地 BERT 和张量 checkpoint 由资产准备脚本生成。
"$PY" "$REPO/scripts/recovery/skill_pipeline/prepare_dino_native_audit_assets.py" \
  --native-checkpoint "$AUDIT/models/groundingdino_swint_ogc.pth" \
  --hf-model "$AUDIT/models/grounding-dino-tiny" \
  --converter-source "$AUDIT/reference/hf_converter.py" \
  --native-source "$AUDIT/reference/GroundingDINO" --output "$AUDIT/native_assets_v3"

"$PY" "$REPO/scripts/recovery/skill_pipeline/audit_dino_native_reference.py" \
  --native-source "$AUDIT/reference/GroundingDINO" \
  --config "$AUDIT/native_assets_v3/native_config_local_bert.py" \
  --checkpoint "$AUDIT/native_assets_v3/native_weights_only.pth" \
  --hf-audit "$AUDIT/hf519_cpu" --evidence "$EVIDENCE" --manifest "$MANIFEST" \
  --output "$AUDIT/native_cpu" --device cpu

# 旧 HF 独立参考调用。
"$PY" "$REPO/scripts/recovery/skill_pipeline/audit_dino_hf_reference.py" \
  --model "$AUDIT/models/grounding-dino-tiny" --reference-audit "$AUDIT/hf519_cpu" \
  --evidence "$EVIDENCE" --manifest "$MANIFEST" --output "$AUDIT/hf440_cpu"
```

以上输出目录已存在，重复实验必须指定新的空目录。当前源码已含空结果修复，重新执行封装审计时该组不再报错；修复前版本保存在 `reference/recovery_backend_before_fix.py`。

## 可视化与下一步判断

`official_reference_failures.png` 并排展示 Native、HF 4.40.2、HF 5.19 的两个错误区域；只画相关 carton / wine bottle 框，其余框仍保留在原始 JSON 和逐帧叠图中。

第一步没有发现“改一个坐标变换或类别索引就能解决全部误检”的问题。下一阶段应以与原仓库对齐的冻结检测基线采集和标注数据，再进行分辨率与微调对照；类别识别效果仍需独立验收。

关联：[上轮查询与阈值对照](rgbd_detection_ablation_20261015.md)，[本轮机器可读摘要](dino_official_entrypoint_20261015_summary.json)。
