---
id: spatial_black_bowl_to_plate_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '^(?:pick|pick up).*black bowl.*place it on the plate'
    - scene_object_matches: '^akita_black_bowl_[0-9]+_main$'
task_binding_profile: spatial_black_bowl_to_plate_v1
---

Bind the black bowl selected by the instruction's reset-time spatial relation, then bind the
unique plate as the placement goal. When strict contact tests do not yield a unique bowl after
position perturbation, rank only the language-matched bowl candidates against the referenced
MuJoCo objects, fixture sites, or estimated table center.
