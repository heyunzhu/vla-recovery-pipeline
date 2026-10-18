---
id: grasp_flat_box_topdown_short_side_deep
name: Flat-box deep top-down short-side grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 55
when_to_apply: When recovery is manipulating a very thin grocery box such as cream cheese, butter, or chocolate pudding and shallow top-edge pinches fail to hold after lift.
when_not_to_apply: Do not use for bowls, mugs, cans, bottles, tall cartons, baskets, trays, or non-box objects.
failure_signature:
  - Recovery reaches the box but lift probe reports lift_probe_unconfirmed or gripper_closed_but_not_holding.
  - The default flat-box grasp closes near the top surface rather than through the box body.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "cream_cheese|cream cheese|butter|chocolate_pudding"
    - target_name_excludes: "alphabet_soup|tomato_sauce|ketchup|milk|orange_juice|bowl|mug|can|bottle"
recovery_hints:
  grasp_profile: flat_box_topdown_short_side_deep_v1
  target: target
  params:
    source: task48_52_57_58_flat_box_shallow_pick_analysis_20260824
evidence:
  tasks:
    - libero_90 task48 pick up the cream cheese box and put it in the basket
    - libero_90 task52 pick up the butter and put it in the basket
    - libero_90 task57 pick up the butter and put it in the tray
    - libero_90 task58 pick up the cream cheese and put it in the tray
    - libero_90 task62 pick up the chocolate pudding and put it in the tray
    - libero_90 task70 put the chocolate pudding to the left of the plate
    - libero_90 task71 put the chocolate pudding to the right of the plate
  episodes:
    - online_skill_regression_tasks47_60_20260824
---

## Intent

This policy contributes only the deep flat-box grasp sampler profile. It keeps
the same task trigger and placement behavior as the active repair skill, but
pushes the close pose down into the box body and keeps long-axis offsets small.

It does not decide when to recover and does not define placement goals or
planner geometry.
