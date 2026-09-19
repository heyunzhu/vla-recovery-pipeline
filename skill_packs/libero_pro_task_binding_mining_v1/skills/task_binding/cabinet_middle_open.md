---
id: cabinet_middle_open_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '^open.*middle (?:drawer|layer)'
    - scene_object_matches: '^wooden_cabinet_[0-9]+_cabinet_middle$'
task_binding_profile: cabinet_middle_open_state_v1
---

Bind an instruction to open the middle cabinet drawer to the matching MuJoCo cabinet link.
The binding records the final state semantics; articulated recovery execution remains a
separate capability.
