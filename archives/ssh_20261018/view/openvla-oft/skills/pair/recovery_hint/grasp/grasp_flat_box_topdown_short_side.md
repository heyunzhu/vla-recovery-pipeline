---
id: grasp_flat_box_topdown_short_side
name: Flat-box top-down short-side grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 52
when_to_apply: When an already-triggered recovery is manipulating a thin rectangular grocery box that has not been promoted to the deep flat-box profile.
when_not_to_apply: Do not use for bowls, mugs, cans, bottles, plates, drawers, baskets, or non-box objects.
failure_signature:
  - Thin grocery boxes can be represented by a rotated MuJoCo box whose local z axis is not world-up.
  - Center-top default grasps can chase the wrong local axis or require an over-wide gripper span.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "cream_cheese|cream cheese|butter|box"
    - target_name_excludes: "alphabet_soup|soup|can|tomato_sauce|ketchup|bottle"
recovery_hints:
  grasp_profile: flat_box_topdown_short_side_v1
  target: target
  params:
    source: task48_cream_cheese_pick_analysis_20260823
evidence:
  tasks:
    - libero_90 task48 pick up the cream cheese box and put it in the basket
  episodes:
    - gpu1_selected_online_mining_clean_task48_20260823
---

## Intent

This policy contributes only the flat-box grasp sampler profile. The sampler
keeps the original collision geometry but samples world-top-down grasps that
span the short side of thin rectangular boxes.

It does not decide when to recover and does not define placement goals or
planner geometry.
