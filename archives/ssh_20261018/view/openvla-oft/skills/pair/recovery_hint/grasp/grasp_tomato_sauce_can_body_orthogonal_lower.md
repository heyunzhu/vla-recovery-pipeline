---
id: grasp_tomato_sauce_can_body_orthogonal_lower
name: Tomato-sauce can orthogonal lower-side grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 57
when_to_apply: When recovery is manipulating tomato sauce and the generic can sampler produces shallow or hard-to-track pick poses.
when_not_to_apply: Do not use for alphabet soup, flat boxes, cartons, bowls, mugs, bottles, baskets, trays, or non-can objects.
failure_signature:
  - Tomato sauce recovery hits optimized_motion_tracking_stalled during Pick.
  - cuTAMP reports robot_to_movables, pos_err, or motion-planning failures around the pick approach.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "tomato_sauce|tomato sauce"
    - target_name_excludes: "alphabet_soup|cream_cheese|butter|milk|orange_juice|bowl|mug|bottle"
recovery_hints:
  grasp_profile: can_body_orthogonal_lower_side_v1
  target: target
  params:
    source: task50_tomato_sauce_tilted_pick_analysis_20260824
evidence:
  tasks:
    - libero_90 task50 pick up the tomato sauce and put it in the basket
  episodes:
    - online_skill_regression_tasks47_60_20260824
---

## Intent

This policy contributes only a more conservative tomato-sauce can grasp profile.
It keeps samples lower on the can body, removes diagonal yaw choices, and keeps
lateral offsets small so the pick approach is easier to track in clutter.

It does not decide when to recover and does not define placement goals or
planner geometry.
