---
id: bowl_stack_support_grounding
name: Bowl stack support grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 44
when_to_apply: When an already-triggered recovery must stack one bowl on another bowl.
when_not_to_apply: Do not use for placing bowls on plates, tables, cabinet tops, drawers, handles, cans, boxes, or non-bowl support objects.
failure_signature:
  - Bowl-stack goals such as On(bowl_a, bowl_b) can fail because the support bowl is a movable object and is not registered as a cuTAMP Surface.
  - The trigger and grasp hint may fire correctly, but cuTAMP reports an unknown surface literal for the second bowl.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: '\bstack\b'
    - target_name_matches: bowl
    - goal_name_matches: bowl
recovery_hints:
  params:
    grounding_profile: bowl_stack_support_v1
evidence:
  tasks:
    - libero_90 task17 stack the black bowl at the front on the black bowl in the middle
    - libero_90 task18 stack the middle black bowl on the back black bowl
  episodes:
    - mining_tasks11_30_20260822_task17_task18_unknown_surface_literal
---

## Intent

This policy contributes only grounding information for bowl-on-bowl stacking
recoveries. It identifies that the second bowl is the semantic support object
for the stack relation.

It does not decide when to recover, does not change the bowl grasp profile, and
does not modify planner geometry. The paired `bowl_stack_support_geometry`
policy owns the temporary support-surface geometry registration.
