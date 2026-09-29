---
id: open_bottom_drawer_geometry_auto
name: Geometry-selected lower-drawer articulation profile
kind: recovery_hint
track: pair
scope: articulation
priority: 50
when_to_apply: When recovery opens the lower drawer of the supported wooden cabinet and current MuJoCo geometry confidently matches an admitted profile.
when_not_to_apply: Do not apply to other drawer levels, cabinet families, closing goals, missing geometry, out-of-distribution geometry, or ambiguous profile scores.
failure_signature:
  - A fixed lower-drawer grasp does not generalize across cabinet poses and obstacle layouts.
recovery_point: After recovery has been requested and current scene geometry has been read, before the articulation problem is built.
applies_to:
  all:
    - task_language_matches: "\\bopen\\b.*\\bbottom drawer\\b.*\\bcabinet\\b"
    - target_name_matches: "^wooden_cabinet_1_(main|cabinet_bottom)$"
recovery_hints:
  params:
    articulation_profile_selector: bottom_drawer_geometry_v1
evidence:
  tasks:
    - lower-drawer MuJoCo geometry from LIBERO-90 task07 and LIBERO goal-task task01
  episodes:
    - task07 seed90 recovery success joint=-0.1403661072
    - goal-task task01 seed51 recovery success joint=-0.1401520520
---

## Intent

Choose an admitted lower-drawer grasp from the live MuJoCo cabinet, handle and
obstacle geometry. Dataset name, suite name and task ID are deliberately not
selection inputs. Ambiguous or out-of-distribution scenes fail closed instead
of silently applying the wrong grasp.
