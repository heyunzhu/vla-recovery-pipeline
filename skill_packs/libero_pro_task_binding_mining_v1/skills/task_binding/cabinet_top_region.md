---
id: cabinet_top_region_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '^\s*(?:put|place).*on\s+(?:the\s+)?top\s+of.*(?:cabinet|drawer)'
    - scene_site_matches: '^wooden_cabinet_[0-9]+_top_side$'
task_binding_profile: cabinet_top_region_v1
---

Bind instructions that place an object on the top surface of the cabinet or drawer fixture.
The rule does not match instructions that merely describe a source object already on top.
