# 固定帧检测对照：准备与运行记录

状态：九帧、四种查询方式、三个文本阈值共 108 组对照完成，已下载结果并目视核对代表帧。仅修改查询方式可以修复三个篮子的类别，但不能可靠修复目标物体识别；候选数量改善含有明显误检，不能视为 recovery 成功。

## 实际结果

固定其余条件、只减少联合查询的干扰类别，三个篮子的标签都从 carton 变为 basket，定位仍在篮子上。以 06 奶酪→篮子为例：原始联合查询 carton=0.475、basket 对应 token=0.241；仅任务类别联合查询 basket=0.417；逐类查询 basket=0.560。这不是空类别文本或名称映射单独造成的问题，原始模型 logits 就偏向 carton。三组 SAM mask 像素数同为 3165，变化主要发生在类别输出。

但是，减少类别和降低阈值会产生明显的错误类别对应：

- 02 酒瓶→碗：仅任务类别联合查询得到 wine bottle=0.374，但框为 `[94.3, -0.1, 194.4, 109.3]`，覆盖机械臂而非左下方酒瓶。逐类查询也在机械臂上输出 bottle=0.399。原始 token 中 wine=0.374、bottle=0.369，说明不是显示层把别的词误映射成瓶子。此前把“出现 bottle 标签”口头称作“找回酒瓶”不准确，以本次叠图核对为准。
- 03 奶酪→木架：逐类查询、文本阈值 0.25 后出现 cheese 与 rack，但 cheese 框覆盖木架、盘子、炉灶，rack 框覆盖黑色柜体。名义类别齐全，实际没有解决目标定位。
- 08 牛奶→篮子：只查询 milk 与 basket 后，篮子被正确定位，但若干饮料瓶、罐头也被标为 milk；不能选择一个最高分框就当作正确目标。
- 04 碗→盘子：十二组配置均没有正确类别候选。遮挡和原始候选定位缺失未被本轮参数变化解决。
- 06 奶酪→篮子：十二组配置均没有 cheese 候选；篮子修复后目标仍然缺失。

可视化位于 `analysis_outputs/rgbd_detection_ablation_20261015/`：

- `basket_verified_comparison.png`：同一帧中篮子类别的改善。
- `bottle_false_positive_comparison.png`：有 bottle 标签却框住机械臂的反例。
- `query_comparison.png`：五个代表帧、三组配置的总览。
- `evidence/run02/`：逐配置 JSON、选取的叠图、所有 mask、预处理输入图、运行环境、源码及命令记录。

以下仅统计“任务所需类别名均出现”，不是定位准确率、绑定成功率或 recovery 成功率：

| 查询方式 | 文本阈值 0.25 | 0.30 | 0.35 |
|---|---:|---:|---:|
| 原全部类别联合 | 4/9 | 2/9 | 2/9 |
| 仅任务类别联合 | 6/9 | 5/9 | 5/9 |
| 全部类别逐类 | 7/9 | 6/9 | 3/9 |
| 仅任务类别逐类 | 7/9 | 6/9 | 3/9 |

7/9 中包括上述机械臂被认成瓶子、柜体被认成架子的案例，因此不能用这个数字宣称识别问题已解决。

本轮支持的结论是：联合提示词配置确实影响类别输出；通用 tiny 检测器在这些帧上还存在严重的语义误检，降低阈值和逐类查询不足以解决；精确文本过滤会进一步减少候选，但不是所有失败的根因。先前把原始酒瓶问题主要解释成遮挡，证据不足：在本轮实际输出中，瓶子类别对应的是机械臂区域。

下一步应保留篮子对照作为配置修复证据，给固定帧建立人工的类别与区域参考，再评估替代检测器或检测后复核，重点验证瓶子、包装物与机器人是否能正确区分。不要立即把“逐类查询 + 0.25”接回 recovery。当前生产 recovery 和冻结历史代码均未修改。

## 实验设计

固定十任务实验中九个实际执行检测的 recovery 首帧 agentview RGB。第十个任务停在语言解析，不纳入检测对照。使用原有 Grounding DINO tiny / SAM2 tiny 权重，不运行模拟器、不执行机械臂动作、不修改 recovery。

每张图比较四种查询方式：原始全部类别联合查询、仅任务类别联合查询、全部类别逐类查询、仅任务类别逐类查询。文本阈值分别为 0.25、0.30、0.35，框阈值固定 0.25，共 108 组结果。同一个查询只运行一次检测前向，再用三个文本阈值处理，避免重复计算改变比较条件。单类别查询结果按类别缓存复用。

保留每个查询的原始 logits、预测框、输入 token、逆标准化后的模型输入图像；每组保存原始框/类别文本/过滤理由、保留类别、SAM mask、有效深度像素数和叠加图。类别存在不代表定位或实例身份正确，不把候选数量当作准确率。

逐帧检查重点是：篮子是否仍被认作 carton、木架空类别是否改变、目标包装盒是否出现正确定位、遮挡盘子是否产生独立框，以及降低阈值是否增加误检/多实例歧义。类别词替换、换模型和新相机未混入本轮实验。

原配置 full_joint / text=0.35 与历史原始框进行复现核验：预设严格要求框坐标误差不超过 0.01 像素，分数误差不超过 1e-4，顺序及文本相同。九帧的框数与类别文本全部一致，但均未满足上述严格数值复现要求；最大框坐标差约 0.0386 像素，最大分数差约 0.00229。原因尚未确定，不标为严格数值复现成功。本轮配置比较均以同一进程内重跑的 full_joint 为基线；没有把新旧运行的细小分数差当成改善。

torch=2.7.1+cu126、transformers=5.19.0，两个模型权重 SHA256 校验通过。目视检查逆标准化的模型输入图像，没有发现明显的上下翻转、RGB/BGR 颜色颠倒或内容错位；这不代替完整的参考实现一致性测试。

初次 run01 在第 04 帧的单类无检测结果时中断。保存的输出形状显示 boxes 为 `(0,4)`、scores 为 `(0,)`，但 labels 含一个空字符串，触发现有后端的长度一致性检查。run02 仅在诊断脚本中把零框、零分数视为无检测，并保存实际形状，完整重新运行全部九帧。run01 原目录及日志保留；没有静默重写历史失败或修改生产后端。

## 已完成的本地检查

- 九张 RGB-D 中的 RGB 数组与历史检测 PNG 逐像素一致。
- 原始数组均为 256×256×3、uint8；没有发现保存图像与本次取图不同的问题。这不等于已经验证模型内部预处理。
- 从语言生成的任务提示词与原始联合提示词中的相应条目一致。
- 用当前类别过滤函数处理历史原始框，九例全部复现历史保留类别。
- 准备模式生成 9 个固定样本和 108 组对照配置；脚本语法检查通过。

准备产物：`analysis_outputs/rgbd_detection_ablation_20261015/prepare/manifest.json` 和 `local_preflight.json`。

## 运行入口

脚本：`scripts/recovery/skill_pipeline/probe_saved_detection_ablation.py`。

本地准备命令：

```powershell
python scripts/recovery/skill_pipeline/probe_saved_detection_ablation.py --evidence analysis_outputs/rgbd_ten_tasks_20261015/evidence --output analysis_outputs/rgbd_detection_ablation_20261015/prepare --prepare-only
```

输出目录必须为空，重复运行使用新目录，保留历史产物。

服务器恢复后，将本脚本同步到独立实验目录，使用已有 Python 3.10 检测环境、依赖和冻结代码执行：

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
export PYTHONPATH="$ROOT/logs/rgbd_exact_box_20261008/pydeps${PYTHONPATH:+:$PYTHONPATH}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
"$ROOT/envs/tiptop-planning-py310/bin/python" \
  "$ROOT/logs/rgbd_detection_ablation_20261015/probe_saved_detection_ablation.py" \
  --evidence "$ROOT/logs/rgbd_ten_tasks_20261015" \
  --output "$ROOT/logs/rgbd_detection_ablation_20261015/run01" \
  --code-root "$ROOT/logs/rgbd_ten_tasks_20261015/visual_code_frozen" \
  --grounding-model-dir "$ROOT/logs/rgbd_exact_box_20261008/models/grounding-dino-tiny" \
  --sam2-model-dir "$ROOT/logs/rgbd_exact_box_20261008/models/sam2.1-hiera-tiny" \
  --device cuda:0
```

上述服务器目录和环境已实时确认，对照已完成。上方示例是首轮入口；实际完成的是 `probe_saved_detection_ablation_v2.py` / `run02`，精确参数、环境变量和脚本哈希保存在服务器独立实验目录的 `command_run02.json`。原始 logits 和所有完整产物留在服务器。

服务器 review_bundle.zip：91,851,477 字节，SHA256 `1423870ee22575f554a86e7d11d60ebb34aed7bed0192c7c36fd7cc99a2762a4`，不含原始模型输出 NPZ，后者仍在原实验目录。

已下载并核验 SHA256 与 ZIP CRC 的精简包 review_compact.zip：21,943,769 字节，SHA256 `6ba350a9aa31a5d2c33c6543a2ce63f33bbcacfcf583ed88181bde3110f1c3bf`。含所有配置结果与 mask、部分叠图及每帧 full_joint 模型输入图；后补的 token_score_spot_checks.json 单独下载，不包含在该 ZIP 哈希中。

## 连接恢复记录

最初已有 xinghanbo-eval SSH 连接返回 255；启智 CLI 对指定实例的状态查询登录失败，最后认证检查为 HTTP 404。用户指出代理应当正常后，进一步核验发现平台登录页面和 PyPI 均可访问，但旧认证接口返回 APISIX 的 404 Route Not Found。将 CLI 从 7.1.1 更新至官方 PyPI 的 7.1.12 并补齐配套 Playwright Chromium 后，实例状态查询恢复，实例在 qb-prod-4090-gpu171 运行。

新节点 SSH bootstrap 未成功，但平台自带 Jupyter Terminal 通道可正常执行命令，GPU 为 RTX 4090，启动对照前仅占用 9 MiB。使用 CLI 自带的 Jupyter 命令执行接口提交本次离线推理，未更改凭据、代理或其他实例。实验目录为 `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_detection_ablation_20261015`。

关联：[固定帧初步目视诊断](rgbd_ten_tasks_visual_diagnosis_20261015.md)。
