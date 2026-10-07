# RGB-D bowl rim candidate v1

独立的视觉候选技能包。入口为 `pack.json`，使用 `rgbd_candidate_pack_v1` 数据格式；通过 `visual_skill_pack.py` 加载，不使用旧 oracle skill loader，不在旧 catalog 或 online index 注册。

## 输入与输出

- 输入：当前 `RGBDObservation`、同一步 `VisualRecoveryHandoff`、有摘要对应的 `VisualDetection` masks。
- selector：使用语言绑定的目标/放置对象视觉 ID，要求当前观察的 bowl → plate、关系 on。属性尚未验证时仍只能候选匹配。
- 几何：调用已有 `make_visible_rim_candidate` 仿真原型，使用可见高处表面点和机器人手部 Y 轴，输出世界系可见碗沿 anchor 及候选位置。
- 对齐约束：同一步/相机/时间/标定/RGB 摘要、机器人状态、mask 摘要及类别/来源、目标点群均值必须与交接包对应。深度 SHA 随输出记录；点群均值检查不等于完整帧内容摘要，应通过共享 provider 获取交接包。
- 参数固定：相对可见碗沿下移 10 mm，机器人手部局部 Z pad offset -3.6 mm，lift 40 mm。参数/参考系/生成器或 online 标志不受支持的更改会拒绝加载。
- pad offset 来源：已审查的 robosuite 1.4.1 PandaGripper 静态模型约定；不是从场景对象 site 读取。尚未迁移到其他机器人或控制器。

## 准入状态

`candidate_only`，`online_enabled=false`，无环境、动作接口或动态代码加载。即使几何生成成功，仍拒绝 online admission；稳定持物、属性/分割语义、接触几何、碰撞净空、视觉规划适配器与执行器均未验收。

这是新的可见碗沿原型封装，**不是旧 stable_outer_topdown_v2 的等价移植**。旧 body-local 采样中的半尺寸、局部方向及 z offset 没有直接套到可见表面中心。

源技能依赖清单与本轮验证见仓库 `docs/rgbd_visual_skill_pack_20261007.md`。
