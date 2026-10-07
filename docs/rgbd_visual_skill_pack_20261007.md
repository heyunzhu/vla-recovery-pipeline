# 独立视觉候选技能包：2026-10-07

## 已完成

建立 `skill_packs/rgbd_bowl_rim_candidate_v1/pack.json` 和独立数据加载器 `visual_skill_pack.py`。在线 recovery admission 报告现会实际运行视觉 selector 并记录候选包状态；离线回放额外运行碗沿几何生成。候选包没有进入 oracle catalog 或 online index，没有启用 skills。

## 任务 1 源包依赖清单

审查源：`libero_spatial_task01_manual_mining_20260913`。

| 源文件 / 能力 | 原依赖 | 本轮处理 |
| --- | --- | --- |
| grasp hint `task01_black_bowl_inward_diagonal_rim.md` | target_name_matches `akita_black_bowl_2`、bddl_goal_surface_matches `plate_1` | 新 selector 使用语言绑定视觉 ID + 当前 bowl/plate 类别和 on 关系；不认为颜色/材质已验证 |
| `code/grasp_profiles.py` inward v1、stable outer v2、low contact v3 | dims、pose、物体局部方向、半尺寸、fallback (0.107,0.107,0.051)m | 未直接迁移。可见点群不是完整尺寸/物体姿态，新包只生成可见碗沿候选 |
| 同上 `_sample`、`pose7_rotation_matrix` | 物体系 → 世界系旋转 | 新 anchor 在世界系；机器人 closing axis 明确为 hand Y，pad offset 为 hand Z |
| `profile_gripper_width` | 真值短边宽度或默认完整尺寸 | 未迁移，不能用可见投影宽度替代接触宽度；仍缺接触几何验收 |
| mixed topdown fallback | 导入 legacy profile adapter | 新包没有调用 legacy sampler |
| `profiles/collision_world.yaml` | 五个具名 ignore_objects 和两个 protected_objects | 未迁移，不用视觉类别批量忽略障碍；扫掠体和未知区域仍阻止准入 |
| wrong-bowl repair skill | 真值 intent、holding、target/static、未来轨迹距离阈值 | 未迁移。没有把 aperture 或局部随动直接当作稳定持物证明；仍用显式 forced query 测试调用边界 |
| `pack.yaml` mining metadata | BDDL target/goal atom 等 | 仅留在源审查资料，新候选 manifest 不读取这些字段 |

这里迁移的是选择机制和参考系表达，尚未迁移源包全套规划/执行行为。

## 验证结果

33 项针对性测试通过：10 项新候选包测试，加上控制器及在线循环测试。覆盖候选匹配和在线拒绝、缺失绑定、过期/歧义 ID、类别不符、manifest 改动、mask 摘要改变、目标深度改变、机器人状态改变、帧时间步/RGB 不符、深度不足。几何生成器输出路径的 mock 测试验证状态传递，不作为抓取几何有效性证据。

真实数据回放输入：`D:\大三上\科研\visual-policy-dual-query-20261004\frames\step000014`。

结果：`D:\大三上\科研\visual-skill-pack-20261007\replay.json`。

- 感知 backend 调用 1 次，共用视觉快照；目标候选 `obj_003`、放置对象候选 `obj_002`。
- 新 selector 状态为 `candidate_match`。
- 几何生成拒绝：`rim goal outside fixed simulation canary bounds`。已有生成器同时限制候选高度及距当前末端位移；本轮不声称已区分是哪一项越界，也不放宽约束。
- online admission 拒绝，新增环境/恢复动作为 0。本轮为本地真实历史数据回放，没有新增服务器试验。
- 依然不证明对象语义、抓取成功、放置成功或完整 recovery 成功。

## 下一步

规划输入应区分“视觉 grasp anchor 候选”和“机器人当前能直接执行的目标”。下一步定义视觉规划问题数据结构，传递当前视觉 ID、可见点群几何、候选参考系与未知区域；再核查真实 cuTAMP 后端的输入契约，避免可见中心伪装成 body pose。候选包完整准入与 A/B/C 成绩仍待完成。
