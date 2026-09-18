---
id: wine_rack_top_region_binding_v1
kind: task_binding
scope: task_binding
priority: 100
track: fail_only
applies_to:
  all:
    - task_language_matches: '^\s*(?:put|place).*(?:on|onto).*(?:wine\s+)?rack'
    - scene_site_matches: '^wine_rack_[0-9]+_top_region$'
task_binding_profile: wine_rack_top_region_v1
---

Bind direct placement-on-rack instructions to the rack's unique top-region site in the current
MuJoCo scene.
