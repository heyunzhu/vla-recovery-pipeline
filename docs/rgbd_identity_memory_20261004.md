# 2026-10-04：初始目标身份记忆的离线诊断

## 为什么需要这个模块

当前视觉 adapter 在每帧重新用任务语言绑定目标。`between` / `next to` 表达可用于最初挑选对象；被选中的对象搬动后，它可能不再满足原相对位置。每帧重新选择可能丢失目标，甚至选到另一个物体。

新增 `VisualIdentityMemory`，仅在第一帧已有有效候选时记住 target/goal ID 和初始选择证据，后续检查这些原 ID 是否仍在当前帧被观察和跟踪。它是**独立的离线诊断模块**，尚未接入默认 adapter、runner、时序持物判断或恢复控制器，也不取代当前绑定结果。

## 行为及边界

- 第一帧无法选定候选，后续不能在动作已经发生后自动选一个新目标，需要显式 reset。
- 当前目标与 goal 必须 observed、last_seen_step 为当前步、identity_status 为 tracked、类别未变化、深度覆盖至少 80%，且有当前 mask 来源记录和有限可见中心。
- 参考物暂时不可见时可以记录初始选择来源，但只报告当前目标/goal 的 ID 候选；不把初始几何当作当前几何。
- 目标或 goal 丢失、类别变化、身份新分配或深度不足时返回 unknown，保持原记忆 ID，不寻找替代物。
- 场景冲突返回 unknown，不能使用历史场景继续。重新出现也只记录 reacquisition_candidate，并保留 requires_identity_reverification。
- 超过 0.5 秒的观测间隔中断连续性。episode、camera、language、标定或 detector backend 变化要求 reset；重复帧使用完整观测与 handoff 摘要校验缓存。

这些规则中的 80% 深度和 0.5 秒阈值为实验条件，尚未校准。记忆依赖已有几何 tracker 提供的 ID，没有新增外观或重识别核验，所以 **identity_continuity_verified 始终为 false**。闭合夹爪、类别相同或 ID 相同都不能确认物理身份、持物和接触。

全部输出保持 holding_verified、goal_verified、planning_allowed、execution_allowed 为 false；初始 black bowl 描述仍未核验。

## 真实数据回放

对保存的 12 次真实 Pi0 查询分别回放原提示词检测和上轮替代描述检测。复用固定 provider 建立各自的 ID 序列，不运行模型、环境或动作。

| 12 帧诊断 | 原描述 | 替代描述 |
| --- | ---: | ---: |
| 第一帧初始候选 | 1 | 1 |
| 原目标及 goal 当前仍被观察/跟踪的候选 | 4 | 5 |
| unknown | 7 | 6 |
| 身份连续性、持物、目标完成已核验 | 0 | 0 |
| 规划/执行授权 | 0 | 0 |

原描述从第 30 步起，替代描述从第 34 步起，记住的目标缺少当前 observed/tracked 证据；第 46/50/54 步两组都是场景拒绝。因此记忆**没有增加这段真实轨迹的可用绑定帧数，也没有修复漏检**。它保留最初选择来源，并正确区分历史 ID 和当前观测。

原描述的本地 ID 为 target=obj_002、goal=obj_003；替代描述为 target=obj_003、goal=obj_001。ID 命名由各自首次检测顺序分配，仅在同一固定 backend 和 episode 内使用，不能跨 detector 配置按 ID 字符串对齐。

## 验证

7 项针对性测试通过：初始相对关系在目标搬动或参考物丢失后不重新应用；当前目标丢失不换成干扰物；重新出现仍待核验；冲突中断连续性；第一帧无法绑定不在后续自动建立新种子；类别/身份/深度异常拒绝；缓存、输入来源、上下文、标定、backend 和时间变化检查。正向移动/遮挡案例是受控 handoff 测试，不是新的真实抓取实验。

真实两组共 24 条输出另外核验：各自记忆 ID 始终一致，所有身份/持物/完成/执行标记均未通过。最终源码已重新回放有效数据，报告包含输入及执行源码哈希。指定三个 oracle 模块导入尝试为 0；此 guard 范围不等于任意 MuJoCo 内存访问审计。

没有改动默认运行路径，本轮未重复运行此前的完整测试。

## 证据与复现

- [原描述的逐帧记忆诊断](rgbd_identity_memory_baseline_20261004.json)
- [替代描述的逐帧记忆诊断](rgbd_identity_memory_candidate_20261004.json)
- [汇总、拒绝原因和源码哈希](rgbd_identity_memory_audit_20261004.json)

在仓库根目录运行：

```powershell
& 'D:\大三上\科研\.venvs\vla-dev\Scripts\python.exe' `
  scripts/recovery/skill_pipeline/replay_visual_identity_memory.py `
  --input-dir 'D:\大三上\科研\visual-policy-48-20261004' `
  --out-file 'D:\大三上\科研\identity-memory-new.json'
```

替代描述额外指定 `--detector-root 'D:\大三上\科研\rgbd-prompt-candidate-20261004'`。输出文件必须未存在。完整原始回放保存在 `D:\大三上\科研\identity_memory_baseline_v2_20261004.json` 和 `identity_memory_candidate_v2_20261004.json`；初版产物保留，v2 包含场景 admission 一致性检查。

## 下一步

继续解决混合标签及遮挡下的当前可见分割证据，再验证出现后的物理身份是否可确认。身份记忆只防止重新选择和历史状态冒充当前状态，不能生成缺失的观测。得到可靠的当前目标与 goal 后，才能推进视觉持物、支撑和任务完成核验。
