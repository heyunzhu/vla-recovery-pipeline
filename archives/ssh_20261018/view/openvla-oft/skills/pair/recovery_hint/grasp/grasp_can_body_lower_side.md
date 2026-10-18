---
id: grasp_can_body_lower_side
name: Can body lower-side grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 53
when_to_apply: When an already-triggered recovery is manipulating a can-like grocery item such as alphabet soup or tomato sauce.
when_not_to_apply: Do not use for flat boxes, bowls, mugs, bottles, plates, drawers, handles, baskets, or non-can objects.
failure_signature:
  - Task47 alphabet-soup recovery was incorrectly matched to the flat-box sampler.
  - The selected close poses were 5-6.5 cm above the object center and repeatedly produced lift_probe_unconfirmed.
  - The object did not follow the lift probe, indicating a high rim/top-edge pinch instead of a stable body grasp.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "alphabet_soup|tomato_sauce|soup|can"
    - target_name_excludes: "cream_cheese|butter|box|bottle"
recovery_hints:
  grasp_profile: can_body_lower_side_v1
  target: target
  params:
    source: task47_alphabet_soup_pick_analysis_20260824
evidence:
  tasks:
    - libero_90 task47 pick up the alphabet soup and put it in the basket
  episodes:
    - online_skill_regression_tasks10_90_20260824_r1_task47
---

## Intent

This policy contributes only the can-body grasp sampler profile. It keeps the
grasp center near the can body and lowers the close height below the top rim so
the gripper pinches the side wall instead of closing on the upper edge.

It does not decide when to recover and does not define placement goals or
planner geometry.
