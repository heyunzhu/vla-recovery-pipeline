---
id: hold_then_pick_traj_opens
name: 抓住后重规划开爪
kind: repair
hook: before_trajectory_step
priority: 100
when_to_apply: 合爪后物体已跟随抬起，下一段却是空手 Pick/MoveFree
when_not_to_apply: 第一次合爪后物体 z 未跟随
failure_signature:
  - object_followed after close
  - next label matches pick( or movefree
recovery_point: 第一次确认抓住之后、第二条 Pick 轨迹开始之前
trigger:
  all:
    - object_followed_lift: true
    - label_matches: "pick\\(|movefree"
    - aperture_gt: 0.02
backend: keep_gripper_closed
evidence:
  tasks: []
  episodes: []
---

Test fixture only. Not admitted to `skills/_index.yaml`.
