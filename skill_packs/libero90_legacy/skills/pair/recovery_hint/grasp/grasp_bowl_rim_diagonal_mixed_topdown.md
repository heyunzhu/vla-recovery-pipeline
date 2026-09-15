---
id: grasp_bowl_rim_diagonal_mixed_topdown
name: Bowl rim diagonal mixed top-down grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 50
when_to_apply: When an already-triggered recovery is manipulating a larger non-white bowl target.
when_not_to_apply: Do not use for the small white bowl, cans, boxes, drawers, handles, or non-bowl objects.
failure_signature:
  - Bowl pick failures were dominated by unstable or empty closes when using generic grasp sampling.
  - A profile sweep on task10, task13, task14, and task15 favored the diagonal mixed top-down rim sampler at 10/12.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "bowl"
    - target_name_excludes: "white_bowl|white bowl"
recovery_hints:
  grasp_profile: bowl_rim_diagonal_mixed_topdown_v1
  target: target
  params:
    source: bowl_grasp_profile_sweep_20260822
evidence:
  tasks:
    - libero_90 task10 put the black bowl on the plate
    - libero_90 task13 put the black bowl at the back on the plate
    - libero_90 task14 put the black bowl at the front on the plate
    - libero_90 task15 put the middle black bowl on the plate
  episodes:
    - bowl_grasp_profiles_tasks10_13_14_15_gpu3_20260822_r1
---

## Intent

This policy contributes only the bowl grasp sampler profile. It does not decide
when to recover and does not define recovery goals.

The sampler implementation remains in the cuTAMP adapter. This skill only says
that bowl-target recoveries should use the diagonal mixed top-down rim profile.
