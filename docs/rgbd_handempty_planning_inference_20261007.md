# 显式夹持模型下的空手规划推断

日期：2026-10-07。

## 新接口

`build_visual_tamp_problem.py --infer-open-pad-handempty` 明确启用空手推断。默认不启用，仍输出未知和空 init_atoms。

推断条件：当前实测两指打开、当前静态pad间隙盒完整在画面中、至少16条相交像素中心射线全部有效且表面在出盒深度后超过2mm。前景遮挡、盒内点、缺深度或闭爪都输出未知。

模型假设明确写入产物：刚性非黏附物体、持握需要两pad相向夹持、物体可由当前深度分辨、静态pad位姿误差不超过深度余量。它不是无条件物理真值，不确认释放成功或此前抓取成功。

生成 `rgbd_open_visible_pad_gap_inference` 来源的 HandEmpty。confidence=自由有效射线比例，明确是覆盖率而非校准后的物理状态概率。后端需要显式 `initial_state_allow_pad_model_inference=true`，并核对匹配的完整帧摘要、快照、原始间隙证据和初始事实；默认配置拒绝这一推断。

此事实允许离线原生规划探索，不能替代运行时持物验证和执行准入。execution_allowed、holding_verified、release_verified 均为false；后续还需验证模型假设适用的任务和误判率。

## 实际结果

同一历史step14，725/725射线自由、两指打开，生成1条模型下推断的HandEmpty。输出：`D:\大三上\科研\visual-tamp-problem-20261007\problem_pad_inferred_v2.json`。保留目标盘碰撞和1806个障碍体素，未调用solver，无新动作。上一份未推断的problem.json保持原样。

20项相关测试及**789项完整skill_pipeline测试通过**。包含默认拒绝、错误帧拒绝、遮挡/闭爪不输出事实。原生环境仍在cuRobo编译，已核对nvcc/cc1plus真实进程；依赖实际解析为torch2.7.1、numpy2.4.6、warp1.12.1、rerun-sdk0.38.1。安装过程升级了NumPy，是否满足实际运行需继续验证，尚未视为兼容完成。

## 独立原生检查任务

提交4e951e2。独立个人目录 `/mnt/sdb/24_yyx/setup/native-visual-world-pad-20261007`，tmux `rgbd-native-pad-20261007`，启动时真实bash PID274701。代码归档两端SHA256：`6011fe0094a87326d554eace2434322f0a9c2497d298d8296d8f5bc7f1611417`。任务跟随当前安装，随后在CPU上构建实际原生世界和初始状态，结果写result.json。

它与原来的未知手状态原生检查分别保留输入、运行代码和结果，部署时均在等待安装，没有原生运行结果。并非A/B/C任务成功率实验。
