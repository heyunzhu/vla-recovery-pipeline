---
id: stove_turn_off_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '^turn off (?:the )?stove$'
    - scene_object_matches: '^flat_stove_[0-9]+_main$'
task_binding_profile: stove_turn_off_state_v1
---

Bind a turn-off instruction to the unique MuJoCo stove and emit the `turnoff` final-state
semantic atom. Switch manipulation remains a separate execution capability.
