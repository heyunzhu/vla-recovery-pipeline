---
id: cabinet_top_support_grounding
name: Cabinet top support grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 45
when_to_apply: When an already-triggered recovery must place an object on top of a cabinet.
when_not_to_apply: Do not use for placing inside drawers, closing drawers, handles, doors, or generic cabinet body interactions.
failure_signature:
  - Coarse cabinet grounding can bind placement to the cabinet body or drawer entities instead of the explicit top support surface.
  - Cabinet-top placement should prefer explicit top support names such as *_cabinet_top or *_top.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "on top of .*cabinet|cabinet top"
recovery_hints:
  params:
    grounding_profile: cabinet_top_support_v1
evidence:
  tasks:
    - libero_90 task16 put the middle black bowl on top of the cabinet
  episodes:
    - top_support_collision_task16_20260822
---

## Intent

This policy contributes only placement-surface grounding preferences for
cabinet-top goals. It does not decide when to recover and does not modify grasp
sampling.
