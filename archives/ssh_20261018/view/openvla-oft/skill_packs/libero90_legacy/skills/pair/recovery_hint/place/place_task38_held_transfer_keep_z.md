---
id: place_task38_held_transfer_keep_z
name: Task38 held bowl transfer keeps height
kind: recovery_hint
track: pair
scope: place
priority: 49
when_to_apply: When recovery has grasped the white bowl for task38 and must move it to the right-of-plate table region without scraping nearby scene geometry.
when_not_to_apply: Do not use as a generic place policy, for caddy compartments, drawer/cabinet placements, or for non-white-bowl targets.
failure_signature:
  - After a successful recovery pick, the held white bowl descends during the transfer toward the right-of-plate region.
  - The bowl can collide with nearby microwave/tabletop geometry before the executor reaches the final place hover/drop stage.
recovery_point: After a repair/trigger skill has already decided to call recovery and after a grasp hint has selected the white-bowl grasp profile.
applies_to:
  all:
    - task_language_matches: "white bowl.*right.*plate|right.*plate.*white bowl"
    - target_name_matches: "white_bowl|white bowl"
recovery_hints:
  params:
    place_profile: task38_held_transfer_keep_z_v1
evidence:
  tasks:
    - libero_90 task38 put the white bowl to the right of the plate
  episodes:
    - task38_plate_region_candidates_gpu0_r1 showed the pick often succeeds, but the bowl can lower and collide during transfer before release.
---

## Intent

This policy contributes only executor-side place transport behavior through
the `task38_held_transfer_keep_z_v1` place profile. It leaves task38
grounding, region geometry, and white-bowl grasp sampling unchanged.

When the executor is already holding the white bowl and is moving toward a
future `Place(...)` action, it replaces the descending held-object transfer
with a protected path: first lift slightly if needed, then translate in XY at
that protected height. The final vertical drop and release are still handled by
the normal place executor.
