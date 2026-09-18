---
id: basket_inside_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '(?:place|put).*(?:in|inside).*basket'
    - scene_object_matches: '^basket_[0-9]+_main$'
task_binding_profile: basket_inside_v1
---

Bind pick-and-place instructions whose destination is the unique basket in the current scene.
The manipulated object is resolved from language; the concrete basket instance is resolved
from the reset-time MuJoCo scene.
