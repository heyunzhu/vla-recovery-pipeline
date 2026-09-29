---
id: open_bottom_drawer_goal_task01_height6_tight
name: LIBERO goal-task lower drawer raised tight articulation profile
kind: recovery_hint
track: pair
scope: articulation
priority: 60
when_to_apply: When recovery opens the lower drawer of the wooden cabinet in the admitted LIBERO-Pro goal-task scene family.
when_not_to_apply: Do not apply to other drawer levels, cabinet families, closing goals, or LIBERO-90 scenes.
failure_signature:
  - The Task-7 candidate contacts the handle but loses the physical envelope during the long pull in goal task01.
recovery_point: After recovery has been requested and before the articulation problem is built.
applies_to:
  all:
    - task_language_matches: "\\bopen\\b.*\\bbottom drawer\\b.*\\bcabinet\\b"
    - target_name_matches: "^wooden_cabinet_1_(main|cabinet_bottom)$"
    - source_suite_is: libero_goal_task
recovery_hints:
  params:
    articulation_profile: bottom_drawer_goal_task01_height6_tight_v1
evidence:
  tasks:
    - libero_goal_task task01 open the bottom drawer of the cabinet
  episodes:
    - seed51-65 recovery 14/15 on 2026-09-29
---

## Intent

Select the raised, tighter handle grasp with a short joint-progress contact
probe. The suite guard is an admission boundary, not a claim that suite names
are the final generalization signal; a future geometry diagnostic should
replace it after cross-scene evidence exists.
