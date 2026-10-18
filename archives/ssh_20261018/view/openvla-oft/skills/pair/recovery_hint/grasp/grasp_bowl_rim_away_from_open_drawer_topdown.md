---
id: grasp_bowl_rim_away_from_open_drawer_topdown
name: Bowl rim away-from-open-drawer top-down grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 56
when_to_apply: When an already-triggered recovery is manipulating a black bowl for a cabinet-top placement and the default-open drawer/cabinet side can block the pick.
when_not_to_apply: Do not use for white bowls, non-bowl objects, plate-only bowl tasks, drawer manipulation tasks, or non-cabinet-top placements.
failure_signature:
  - Task32 recovery escaped the default-open drawer, but the following generic bowl grasp could still approach from the drawer/cabinet side.
  - cuTAMP produced feasible plans, while videos showed execution contact near the open drawer during the regrasp.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "bowl"
    - target_name_excludes: "white_bowl|white bowl"
    - task_language_matches: "on top of .*cabinet|cabinet top"
recovery_hints:
  grasp_profile: bowl_rim_away_from_open_drawer_topdown_v1
  target: target
  params:
    source: task32_open_drawer_side_pick_analysis_20260829
evidence:
  tasks:
    - libero_90 task32 put the black bowl on top of the cabinet
  episodes:
    - online_skill_regression_tasks30_90_selected_20260829 task32 ep00-ep04
---

## Intent

This policy contributes only the cabinet-top/open-drawer bowl grasp sampler.
It keeps the same top-down rim family as the generic black-bowl skill, but
prefers rim samples whose world-frame Y offset is away from the cabinet/drawer
side and narrows yaw to a radial jaw-axis pair.

It does not decide when recovery should start, change the drawer-blocker repair
trigger, bind placement targets, or alter cabinet geometry.
