# 通用skill调研案例集：cabinet触发与薄盒抓放

日期：2026-10-13。只读调查，不修改技能库，不跑新实验。

## 核查状态与证据等级

- **S（源码/配置）**：本轮实际读取本地文件确认实现与差异。
- **H（历史记录）**：skill作者、findings、bundle或复盘中记载的轨迹与成绩；本轮尚未用原始episode/score重新核验。
- **R（原始运行验证）**：需要按task/seed/init身份、命令、版本、admission与逐集记录复核；本轮两案例的生产历史尚未达到R级。

原实例实时查询STOPPED；未擅自启动。远端核查需用户允许启动原实例只读访问，且历史旧路径存在迁移风险。以下是在本地能补齐的完整叙事，不把H级数据伪称R级结论。

## 案例A：cabinet-top错误目标接管

### 身份

任务是“从柜顶取目标黑碗并放到盘子”，不是“把碗放上柜顶”。本地证据来自 `skill_packs/libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914`。历史mining的task4/task5编号沿用当时记录，不与20261011冻结lex编号混用。

### 生产链

| 环节 | 找到的记录 | 等级及限制 |
|---|---|---|
|原task4 baseline|skill记录skills-off 0/15，旧库W0也0/15，seed51–65|H；原baseline目录、命令与逐集结果待定位|
|失败机制|目标为第二个黑碗、goal为plate，意图指向另一个黑碗，目标静止；通用bowl入口要求接近真目标，所以不触发|H；需原query trace验证持续窗口|
|后端可行性probe|强制q5、seed51–55记录5/5，复用hollow bowl抓取与plate放置|H；强制probe不等于自然触发15集验证，skill中列出的自然first-match q5/q6/q10也不等于强制query|
|候选1|cabinet trigger，priority72、错误intent持续≥4等，复用entry repair profile|S；没有新抓取代码|
|新task5旧库表现|wooden-cabinet baseline0/15，W0为5/15；seed51/57/61/63失败q6–q8未触发|H；不是candidate1全范围回归|
|候选2|wooden early trigger修改4个距离/margin阈值、priority78，并约束wooden cabinet语言|S；为错过窗口的专用修补|
|入库结果|本地已有相应skill文件及索引；未找到原admission verdict/raw scan|不能用文件存在证明入库门禁通过或线上晋升|
|自然validation|两候选生产时的完整score、逐集结果尚未定位|待R核查，不编造candidate2最终15集成绩|
|后续C4审计|cabinet winner后6/6，wooden early4/5，来自Core60触发目录|H；已见测试条件的使用相关性，非单skill因果收益或held-out泛化|

### 候选差异（S）

| 字段 | cabinet | wooden early |
|---|---:|---:|
|priority|72|78|
|wrong-object intent margin >|0.10m|0.08m|
|intent future XY distance <|0.12m|0.06m|
|true target future XY distance >|0.18m|0.10m|
|target–EE distance >|0.18m|0.12m|
|错误意图持续query数 ≥|4|4|
|repair profile|entry_lift_open_hand_small_v1|相同|

后者显式限制wooden-cabinet措辞。文末解释这是为了不命中已经保护的task4成功run。它与当前严格保护非当前success winner的admission设计相符，但本轮未见当时admission报告，不能断言候选曾因此被拒绝。

### 可支持与不可支持的判断

支持：两者主要在调用时机/覆盖窗口不同，共用恢复执行路径。应先研究“状态证据能否替代语言特化”，不是先重写抓取算法。

不支持：只删去wooden限制、合并为宽trigger就更好；调阈值一定是过拟合；强制5/5证明所有新layout可行。

### 已定位开发案例与缺口

- 作者记录的no-fire：task5 ep0/seed51、ep6/seed57、ep10/seed61、ep12/seed63。
- 作者记录的W0成功对照：seed52、55、59、65。
- 负例要求：正常接近正确目标、已持物、不同goal、非柜顶初态。当前只找到when_not_to_apply文字，没有每类反例实际执行结果。
- 未见评测：换措辞/参照关系/柜体及高度的独立划分尚未建立；现有Core60不能直接充当未见集。

本地来源：

- [cabinet候选](../../skill_packs/libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914/skills/fail_only/trigger/black_bowl_cabinet_top_to_plate_wrong_object_handoff.md)
- [wooden early候选](../../skill_packs/libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914/skills/fail_only/trigger/black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff.md)
- [C4覆盖审计](../results/libero_pro_c4_skill_trigger_catalog_and_generalization.md)

## 案例B：cream-cheese薄盒抓取与bowl放置

### 身份与可追踪路径

goal_swap task07，put the cream cheese in the bowl，seed51–65。本地pack：`skill_packs/libero_goal_swap_task07_seed51_65_v1`。

复盘记录的旧run：`/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_swap_task07_seed51_65_mining_32486bb_20260910_2145`。当前启智canonical根目录不同，不能直接假定已迁移到对应hdd目录；启动只读核查后应先定位迁移清单/实际目录。

### 三轮生产链

| 阶段 | 作者记录结果 | 新变化 | 支持的失败诊断 |
|---|---:|---|---|
|baseline|0/15|recovery关闭|意图常指向酒瓶/其他碗，奶酪几乎静止|
|W1|6/15|wrong-object trigger + flat-box grasp代码 + bowl support grounding/geometry|进入恢复后，后续放置仍失败|
|W2|8/15|复用W1入口和抓取，仅增加hover/drop预算与release高度容忍|已有抓取路径不能消除有限预算和释放条件问题|
|W3|11/15|复用入口，降低hover高度、重新分配lift/hover/drop预算|修补放置阶段，复盘记载达到阈值|

上述成绩均为H级：baseline来自findings，W1/W2来自后续候选failure_signature，W3来自复盘；尚未核验原score、episode身份、配置一致性及admission。

W1是多层bundle，所以0→6成功不能归因于grasp代码单项。W2/W3的改动对象是place，不是持续改进grasp；缺少受控消融与重复执行，仍不能把6→8→11当作严格因果效应。

### W1真实可执行实现（S）

- `code/grasp_profiles.py`：使用dims及pose判断当前竖直轴、平面长轴，计算采样位置/yaw及夹爪宽度。
- 几何参数化：抓取偏移按物体半尺寸计算，而非只用固定绝对xyz。
- 特化仍在：缺省尺寸(0.080,0.055,0.020)m、深度系数−0.35/−0.15、长轴偏移±0.08、width=2.25×短半轴夹限[0.025,0.075]m等。物体材质、摩擦、质量/重心与接触可行性不是这些参数的自动保证。
- grounding/geometry将目标碗解释为支撑对象与可放置表面；需要核对这一表示和“放进碗”的成功条件是否兼容，不能扩大为任意容器。
- code_patch_manifest列出grasp、grounding、geometry、capability变更边界；历史字段`change_types`需与当时解析实现对应，不能按当前schema直接宣称有效或无效。

### W2/W3配置差异（S）

| place字段 | W2 | W3 |
|---|---:|---:|
|hint priority|43|44|
|hover clearance|未显式指定（作者称默认8cm）|0.045m|
|lift max steps|50|40|
|hover max steps|80|50|
|lift clearance min|0.025m|0.012m|
|hover reached tolerance|0.015m|0.020m|

两者仍限定奶酪→碗；W3注明通过更高priority覆盖W2。higher priority hint合并与实际executor行为需原trace核验，文件说明不能代替运行证据。

### 开发案例、保持案例和未见案例

- W1放置失败（作者记录）：ep00/01/02/05 hover/XY预算耗尽；ep03/12/14 release高度约7.7–8.7cm越过默认7cm；ep07/10 lift clearance问题。
- W2剩余失败：ep00/05/11 hover耗掉余下200step；ep03位于opening XY但高出support约10.8cm，无有效drop预算。
- 这些episode已经被用于候选生成，属于开发/旧能力回归素材，不能称held-out。
- 新薄盒对象、新尺寸/姿态/摩擦、新容器或goal没有独立生产可见范围与测试划分。新seed只改变布局，不自动构成跨对象泛化。
- 负例应包含超出夹爪宽度、不可达/被遮挡、已持有错误物体、非开放容器等。当前源码范围与文档排除条款存在，但未找到系统性执行反例集。

### 入库/线上身份问题

当前本地`skills/_index.yaml`有W1及W2/W3的fail_only条目，但`online: []`。因此“历史mining通过”与“被online生产加载”必须分开。该pack后来还加入了其他task条目；现有整包不是每个W阶段的冻结快照。

本地没有原W1/W2/W3 actor_prompt、当时pack哈希、admission报告或mine_state/score完整链。不能把现在的actor.md倒推成当时生成器实际看过的上下文。

本地来源：

- [W1 findings](../../skill_packs/libero_goal_swap_task07_seed51_65_v1/drafts/findings.md)
- [W1 bundle](../../skill_packs/libero_goal_swap_task07_seed51_65_v1/drafts/bundle.yaml)
- [W2候选](../../skill_packs/libero_goal_swap_task07_seed51_65_v1/drafts/place/cream_cheese_bowl_hover_drop_budget.md)
- [W3候选](../../skill_packs/libero_goal_swap_task07_seed51_65_v1/drafts/place/cream_cheese_bowl_low_hover_balanced.md)
- [抓取实现](../../skill_packs/libero_goal_swap_task07_seed51_65_v1/code/grasp_profiles.py)
- [place配置](../../skill_packs/libero_goal_swap_task07_seed51_65_v1/profiles/place.yaml)
- [历史复盘](../libero_pro_mining_retrospective_2026-09-12.md)

## 远端补齐清单与验收口径

1. 定位真实历史run，校验task语义/BDDL/seed/init身份，保留旧路径与迁移路径映射。
2. 收集baseline及W0/W1/W2/W3 resolved命令、pack/code/hash快照或patch记录；不能用终态pack冒充早期版本。
3. 收集当时actor_prompt、pair/fail_set、findings；区分生成可见与留出材料。
4. 收集admission/code-admission verdict、扫描语料与reject原因；若没运行门禁，则记录未运行，不能补写通过。
5. 扫描逐集episode/query/recovery身份、完成性、基础设施异常，复算成功率与接管时间、hint来源；比对mine_state/score。
6. 每类至少抽查作者列出的失败和旧成功轨迹；恢复代码/配置变化到对应轮次。没有版本快照时标记因果归因受限。

截至本轮，本地生产链与实现层已整理，原始运行验证和历史上下文仍未补齐。后续调研应先完成此清单，再决定改trigger、grasp算法还是place策略；不建议先开展库级自动合并。

## 启动只读核查的状态

用户随后明确授权“启动并检查”。本轮重新读取项目合同及inspire参考，实时确认原实例STOPPED后，仅提交一次原实例start（`--no-wait --post-start none`），未改变规格/镜像/priority。平台接受启动请求，但后续三次实时核验均为PENDING，无节点落点；尚不能访问远端文件。准备的`tmp/inspire/locate_case_history.py`是有界只读目录查找脚本，尚未在远端执行。没有新实验、恢复mining或修改远端资产。远端证据补齐仍待实例实际进入RUNNING，不能将启动请求成功等同于只读核查完成。
