---
id: cabinet_bottom_open_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '^open.*bottom (?:drawer|layer)'
    - scene_object_matches: '^wooden_cabinet_[0-9]+_cabinet_bottom$'
task_binding_profile: cabinet_bottom_open_state_v1
---

Bind an instruction to open the bottom cabinet drawer to the matching MuJoCo cabinet link.
The binding records the final state semantics; articulated recovery execution remains a
separate capability.
