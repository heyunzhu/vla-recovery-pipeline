---
id: open_bottom_drawer_libero90_c8
name: LIBERO-90 lower drawer candidate-8 articulation profile
kind: recovery_hint
track: pair
scope: articulation
priority: 50
when_to_apply: When recovery opens the lower drawer of the wooden cabinet in the admitted LIBERO-90 scene family.
when_not_to_apply: Do not apply to other drawer levels, cabinet families, closing goals, or LIBERO-Pro goal-task scenes.
failure_signature:
  - A generic articulation grasp does not preserve bilateral handle contact through the full lower-drawer pull.
recovery_point: After recovery has been requested and before the articulation problem is built.
applies_to:
  all:
    - task_language_matches: "\\bopen\\b.*\\bbottom drawer\\b.*\\bcabinet\\b"
    - target_name_matches: "^wooden_cabinet_1_(main|cabinet_bottom)$"
    - source_suite_is: libero_90
recovery_hints:
  params:
    articulation_profile: bottom_drawer_contact_c8_v1
evidence:
  tasks:
    - libero_90 task07 open the bottom drawer of the cabinet
  episodes:
    - clean_branch_task07_20260928 seed90 recovery success joint=-0.1403661072
---

## Intent

Select the Task-7-validated candidate-8 handle grasp. The skill does not own
the open predicate, joint binding implementation, cuTAMP operator, cuRobo
planner, or success predicate; those remain generic articulation machinery.
