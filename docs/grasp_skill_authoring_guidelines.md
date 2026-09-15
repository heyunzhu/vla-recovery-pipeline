# Grasp Skill Authoring Guidelines

更新日期：2026-09-12

本文给后续 Codex / agent 编写 `grasp` recovery hint 使用。核心要求是：

> 根据实际失败，或对象几何与默认采样的具体不匹配，画清候选点并验证假设，再写 pack-local profile。

关闭 recovery 的 baseline
没有 pick 失败记录，不能据此排除 grasp。允许读取尺寸、姿态与默认采样代码发现能力缺口，
在同一次介入内用固定 probe 验证；不要求先交一版 repair 才能调查抓取。

`grasp` skill 不负责触发 recovery。它只在 recovery 已经发生后，影响 cuTAMP 选择怎样抓目标。

## 1. 当前运行位置

`grasp` skill 必须写在 active skill pack 下面。常见位置：

```text
skill_packs/libero90_legacy/skills/pair/recovery_hint/grasp/
skill_packs/generated_v1/skills/pair/recovery_hint/grasp/
```

是否 online 只看该 pack 的 `skills/_index.yaml`。目录里有 `.md` 文件但没有进 `online:`
列表时，它不会被 `--enable_skills` 加载。

已入库 grasp skill 的 Markdown 只声明：

```yaml
recovery_hints:
  grasp_profile: <registered_profile>
```

profile 的实现和注册在当前 skill pack 中：

```text
skill_packs/<pack>/code/grasp_profiles.py
skill_packs/<pack>/capabilities.yaml
```

`experiments/robot/libero/tiptop_repro/grasp_profiles.py` 现在是共享 bridge / registry /
默认 `libero_topdown` 实现，不再承载 benchmark-specific grasp 采样。新增对象特化采样时，
优先放到 pack-local adapter；约定路径 `code/grasp_profiles.py` 会自动发现，需声明 PROFILE_IDS、
实现协议函数并注册 capabilities。只有非约定路径才需要显式 adapter 配置。

## 2. 职责边界

`grasp` skill 负责：

- 选择 `recovery_hints.grasp_profile`；
- 约束抓取候选点、yaw、深度、高度；
- 必要时带少量 close / lift / transfer safety executor 参数；
- 描述适用对象、姿态、失败现象和实验证据。

`grasp` skill 不负责：

- 判断什么时候进入 recovery；
- 修改目标绑定；
- 构造 place region / support surface；
- 修复 BDDL grounding；
- 释放前 XY 对齐；
- 绕过 collision / IK 约束；
- 硬编码 query、seed、绝对坐标。

如果问题本质不是抓取，应转给对应类别：

| 问题 | 应写 |
| --- | --- |
| 触发太早/太晚/没触发 | `<pack>/skills/pair/repair/` |
| 目标对象或目标 surface 绑定错 | `<pack>/skills/pair/recovery_hint/grounding/` |
| planner 几何区域缺失或错误 | `<pack>/skills/pair/recovery_hint/geometry/` |
| holding 后释放前需要局部对齐 | `<pack>/skills/pair/recovery_hint/place/` |

## 3. 输入材料

编写 grasp 前必须检查：

| 材料 | 用途 |
| --- | --- |
| 失败视频或关键帧 | 判断错误是否发生在 approach / close / lift。 |
| 同 task 多条失败 episode | 看抓取失败是否稳定复现。 |
| 成功 episode，若存在 | 对比成功抓点、yaw、高度和失败抓点差异。 |
| `query_trace.jsonl` | 看 target、orientation、holding、object_followed、gripper aperture。 |
| `recovery_trace.jsonl` | 看 recovery 是否进入 pick、close、lift，在哪一步退出。 |
| `.problem.json` / `cutamp_debug` | 看候选 grasp 数量、profile、目标几何。 |
| 当前 online grasp skills | 避免重复写，检查 priority / overlap。 |
| 可视化脚本输出 | 画出物体尺寸、候选点、yaw。 |

禁止只凭 task 名称或单条 trace 写 grasp。

## 4. 标准编写流程

### 4.1 先确认是抓取问题

至少回答：

- 夹爪是否接近了正确目标？
- close 前抓取点是否偏高、偏浅、偏到错误几何？
- close 时 yaw 是否导致夹爪沿错误方向闭合？
- close 后目标是否随夹爪上抬？
- 失败是否发生在 pick/lift，而不是 transfer/place？
- 强制更早 recovery 后，抓取问题是否仍存在？

如果没有进入 pick，先分清是 baseline 关闭了 recovery、规划阶段就失败，还是 grasp 确实
不相关。默认候选与目标形状不匹配可以作为 grasp 假设，通过 probe/replay 检验；不能因
缺少执行记录就停止分析。pick 稳定且仅 place 失败时，除非有新的抓取/放置耦合证据，不改 grasp。

### 4.2 识别对象几何和姿态

每个 grasp profile 必须明确自己假设的对象几何：

| 对象 | 需要确认 |
| --- | --- |
| bowl | rim 半径、碗高、是否 shallow、是否 white bowl。 |
| flat box | 长边/短边/厚度、是否需要更深 close。 |
| book | 当前是立着还是倒着，是否需要薄边沿目标方向。 |
| can | 圆柱侧壁高度，是否需要低位或正交 yaw。 |
| carton | upright/fallen，是否有顶部棱，是否避免抓棱。 |
| mug / cup | handle 是否进入 AABB，body-side 是否比 handle-only 更可行。 |
| moka pot | handle 几何方向，是否只允许抓 handle。 |

姿态相关 skill 必须把姿态写进 `applies_to`，例如：

```yaml
applies_to:
  all:
    - target_name_matches: "milk|orange_juice|carton"
    - target_orientation_is: upright
```

### 4.3 画候选点

写 profile 之前先可视化，至少输出：

- object frame / world frame 尺寸；
- 每个候选点 xyz；
- 每个候选 yaw 的闭合方向；
- gripper width；
- 候选点数量；
- 哪些候选预计会失败，为什么。

现有脚本例子：

```bash
python scripts/recovery/skill_pipeline/visualize_bowl_grasp_model.py ...
python scripts/recovery/skill_pipeline/visualize_moka_pot_grasp_model.py ...
```

如果没有对应对象的可视化脚本，先写诊断脚本，不要直接入库 profile。

### 4.4 设计少量可解释候选

优先少量稳定候选，而不是盲目增加搜索空间。

推荐写法：

| 类型 | 候选设计 |
| --- | --- |
| bowl | rim 上选若干方向；区分 radial / tangent yaw；white shallow bowl 单独 profile。 |
| open-drawer bowl | 只选远离抽屉的一侧，不让 generic bowl 覆盖。 |
| flat box | topdown，沿短边夹，必要时把 z 往盒体内取深。 |
| book | topdown short-side，和后续 place footprint/yaw 约束一致。 |
| can | body lower side；特殊 tomato sauce 可用更低、更正交 yaw。 |
| carton | upright/fallen 拆开；upright 避免顶部 gable ridge；fallen 从倒下后的 body side 抓。 |
| mug | body-side baseline 优先；handle-only 必须先证明有足够可行解。 |
| moka pot | 只在 handle 上放候选点。 |

反模式：

- 一个 profile 覆盖 bowl、mug、box、carton 多类对象；
- 用 `target_name_matches: ".+"`；
- 候选点超过 64 但没有 sweep 证据；
- profile 只在 debug problem 里可见，真实 cuTAMP 没用；
- 把目标区域、collision、place z 一起塞进 grasp skill。

### 4.5 写 pack-local profile

benchmark-specific profile 逻辑只写在 active skill pack 的 adapter 中：

```text
skill_packs/<pack>/code/grasp_profiles.py
```

必须同时支持：

```python
sample_grasp_profile(profile, dims, rim=..., pose=...)
sample_grasp_profile_xyzrpy(profile, dims, rim=..., pose=...)
profile_gripper_width(profile, dims, rim=..., pose=...)
```

这样 `tamp_scene.py` 的 problem/debug 候选和 `real_cutamp_backend.py` 的真实 6DoF 采样才一致。
不要分别在 `tamp_scene.py` 和 `real_cutamp_backend.py` 里手写两套候选逻辑。

### 4.6 写 markdown skill

模板：

```yaml
---
id: grasp_<object>_<strategy>
name: <Object strategy grasp>
kind: recovery_hint
track: pair
scope: grasp
priority: <priority>
when_to_apply: ...
when_not_to_apply: ...
failure_signature:
  - ...
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "<target-regex>"
    - target_name_excludes: "<known-non-targets>"
recovery_hints:
  grasp_profile: <profile_name>
  target: target
  params:
    source: <run_or_analysis_id>
evidence:
  tasks:
    - ...
  episodes:
    - ...
---

## Intent

...
```

如果需要 executor 参数，只能用 grasp allowlist，例如：

```yaml
recovery_hints:
  grasp_profile: flat_box_topdown_short_side_book_v1
  target: target
  params:
    executor:
      grasp_close_max_above_m: 0.20
    source: ...
```

## 5. 验证流程

每个 grasp skill 至少走四步：

1. **静态 gate**
   跑：

   ```bash
   python scripts/recovery/skill_pipeline/check_grasp_skills.py --skill_pack <pack>
   ```

2. **profile 单测**
   至少覆盖 sample count、xyz/rpy finite、gripper width、关键 yaw/height。

3. **trace scan / canary**
   检查新 skill 是否抢占已有对象，例如 generic bowl 不能抢 white bowl。

4. **小规模 online 验证**
   用同 init 或 forced recovery，看 close 后 object 是否跟随、lift 是否稳定、是否破坏后续 place。

如果 grasp 改动没有提升 close/lift，先回到可视化和候选点，不要继续加 trigger 或 geometry 补丁。

## 6. Evidence 写法

正文必须包含以下内容：

```markdown
## Visual Diagnosis

- Source videos / frames: ...
- Compared episodes: ...
- Failure at: approach / close / lift
- Good grasp looks like: ...
- Bad grasp looks like: ...

## Geometry And Candidate Design

- Object dimensions: ...
- Candidate points: ...
- Yaw family: radial / tangent / short-side / handle-only / body-side
- Gripper width: ...
- Candidate count: ...

## Validation

- Static gate: ...
- Profile tests: ...
- Online run: ...
- Close/lift outcome: ...

## Boundaries

- Does not trigger recovery.
- Does not change grounding / geometry / place.
- Should be overridden by ...
- Should not match ...
```

## 7. 当前类别经验

### Bowl

通用 bowl profile 只能覆盖黑碗等普通 bowl，并必须排除 `white_bowl`。white shallow bowl
用单独 profile。task38 这种靠微波炉场景可以复用 white bowl profile，但额外加抓后上抬。

### Flat Box

早期 `flat_box_topdown_short_side_v1` 抓取偏浅，后续多数盒状物应让 deep 版本以更高
priority 覆盖。不要让 flat-box profile 匹配 can、carton、mug、bowl。

### Book

book-to-caddy 不是普通 flat box。grasp 的 thin-side 约束要和 place footprint/yaw
保持一致，否则抓住以后仍可能横不过目标开口。

### Carton

不要再使用旧的 `carton_body_vertical_deep` 单一 profile。carton 必须按 upright/fallen
拆开，upright 避免顶部棱，fallen 按倒下后的 body side 抓。

### Mug

当前 online 使用 body-side baseline。handle-only 曾经做过 sweep，但可行解少，不能作为默认。
如果以后重新写 handle grasp，必须先证明该场景的 handle 方向稳定且 planner 有足够可行粒子。

## 8. 最小交付物

Codex 写 grasp skill 时至少交付：

1. `<pack>/skills/pair/recovery_hint/grasp/*.md` 或 draft。
2. 对应 active skill pack 的 `code/grasp_profiles.py` profile 实现。
3. profile 单测。
4. 候选点可视化或截图路径。
5. `check_grasp_skills.py` 静态 gate 结果。
6. 小规模 online 验证结果和视频路径。
