---
id: stove_cook_region_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '^\s*(?:put|place).*(?:on|onto).*stove'
    - scene_site_matches: '^flat_stove_[0-9]+_cook_region$'
task_binding_profile: stove_cook_region_v1
---

Bind direct placement-on-stove instructions to the unique cook-region site exposed by the
current MuJoCo stove fixture. This rule deliberately excludes front-of-stove instructions.
