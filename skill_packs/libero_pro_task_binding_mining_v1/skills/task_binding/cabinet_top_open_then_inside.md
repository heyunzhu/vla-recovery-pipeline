---
id: cabinet_top_open_then_inside_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '^open.*top (?:drawer|layer).*(?:put|place).*inside'
    - scene_object_matches: '^wooden_cabinet_[0-9]+_cabinet_top$'
task_binding_profile: cabinet_top_open_then_inside_v1
---

Bind the object named after “put” to the top cabinet compartment, preserving both final
requirements: the object is inside and the compartment is open. Articulated execution stays
outside this semantic binding skill.
