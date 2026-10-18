---
id: shelf_support_grounding
name: Two-layer shelf support grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 45
when_to_apply: When an already-triggered recovery must place a book on a
  two-layer shelf support surface.
when_not_to_apply: Do not use for desk caddies, baskets, drawers, bowls,
  plates, or cabinet-top tasks.
failure_signature:
  - LIBERO-90 task88 uses an explicit wooden_two_layer_shelf top-side support.
  - Parser fallbacks may bind coarse shelf language to the shelf body instead
    of the support surface.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "shelf|cabinet shelf"
    - target_name_matches: "book"
recovery_hints:
  params:
    grounding_profile: shelf_support_v1
evidence:
  tasks:
    - libero_90 task88 pick up the book on the left and place it on top of the shelf
  episodes:
    - online_skill_regression_tasks81_90_scopefix_20260829 task88 r0
---

## Intent

This policy only contributes placement-surface grounding for two-layer shelf
book tasks. It does not decide when to recover and does not create virtual
geometry for inside-region shelf goals.
