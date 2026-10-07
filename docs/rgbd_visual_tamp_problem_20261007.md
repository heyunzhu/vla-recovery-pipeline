# RGB-D 到正式 TAMPProblem 的转换记录

日期：2026-10-07。阶段：离线场景转换完成，原生规划和在线执行未验收。

## 本次做了什么

`visual_tamp_adapter.py` 将同一 RGB-D 快照的语言绑定、可见物体点群、工作空间点群、机器人关节状态转换为正式 `TAMPProblem`。转换前检查完整帧摘要、快照编号、关节限位及点群确实来自当前深度。机器人自身像素仅按已核对的当前静态模型投影证据剔除。

物体代理在机器人基座候选坐标系下由可见点群包围盒生成，加入 3mm 边界。代理中心不是物体真实 body 原点；可见盒也不代表完整物体形状或容器内腔。未命名的剩余工作空间点群全部转换成 2cm 占据体素，超出预算明确失败，不丢弃障碍。

`visual_cutamp_world.py` 将上述代理转换为原生 `Cuboid` 和 `TAMPEnvironment`。正式后端在 `initial_state_source=rgbd_observed` 时进入该分支，绕过旧名称推断、MuJoCo 几何、默认桌面和默认 dummy obstacle。目标盘仍参与碰撞，未引入隐式接触豁免。

## 实际历史帧结果

输出：`D:\大三上\科研\visual-tamp-problem-20261007\problem.json`。

输入：`visual-policy-dual-query-20261004/frames/step000014/observation`，共享视觉规划证据来自 `visual-panda-ik-20261007/planning`。

| 项目 | 数量 / 状态 |
|---|---|
| 目标碗 obj_003 | 2,994 个可见点，1 个 movable |
| 目标盘 obj_002 | 5,262 个可见点，1 个 surface |
| 其他语义物体 | 2 个 static context |
| 未命名障碍 | 1,806 个占据体素 |
| static 总数 | 1,808；原生世界另保留目标盘碰撞 |
| 残余工作空间点 | 159,347 |
| 剔除的工作空间机器人点 | 12,370；区别于全帧 15,319 个匹配像素 |
| 初始持物状态 | unknown，init_atoms 为空 |
| oracle 导入拦截尝试 | 0 |
| solver 调用 / 新环境动作 | 0 / 0 |

完整帧 SHA256：`3a04904f2ac13be126df68868380af560c33c7761bc5a250e61c8f61d3861467`。

## 验证与限制

完整 skill_pipeline 测试 **780 项通过**，其中新增 5 项覆盖实际测量坐标变换、角色绑定、修改帧/注入点/重复 ID 拒绝、体素覆盖及预算失败、正式后端分支与目标盘碰撞保留。原生类型测试使用替身验证接口组装，不能替代安装后的原生运行。

服务器个人 tmux `rgbd-planner-setup-20261007` 仍处于 torch_install，下载目录已到 1.2GB；无 GPU 任务。安装完成后还需检查实际 API、碰撞缓存容量、编译扩展及运行版本。

当前 `solver_initial_state_ready=false`、`execution_allowed=false`。没有观测到可靠 HandEmpty；隐藏空间、独立基座标定、碗沿抓取与放置约束、完整路径碰撞、视觉动作后验证仍未验收。TAMPProblem 兼容结构中旧 table_z 默认值未被视觉世界消费，未据此合成桌面。原生 box grasp sampler 的配置也不代表已接入并验证碗沿技能。

本次不计入在线恢复成功样本。迁移尚需正式规划、执行器、容器闭环，以及同条件 A/B/C 和 held-out 实验。
