---
id: stove_front_table_region_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '^(?:push|put|move).*to (?:the )?front of (?:the )?stove'
    - scene_object_matches: '^flat_stove_[0-9]+_main$'
    - scene_object_matches: '^flat_stove_[0-9]+_button$'
    - scene_site_matches: '^flat_stove_[0-9]+_cook_region$'
task_binding_profile: stove_front_table_region_v1
---

Bind the object named by the instruction to a virtual table region in front of the stove.
Derive the front direction at reset time from the MuJoCo cook-region and button geometry; do
not reuse a BDDL region, task coordinate, or concrete instance.
