---
id: wine_rack_top_region_grounding
name: Wine rack top-region grounding
kind: recovery_hint
track: fail_only
scope: grounding
priority: 67
when_to_apply: When a wine-bottle-on-rack recovery has fired and the task BDDL names
  `wine_rack_1_top_region`, but the semantic/parser goal has collapsed to `wine_rack_1_main`.
when_not_to_apply: Do not use for cabinet-top wine-bottle tasks, bowls, mugs, cream
  cheese, flat boxes, books, cans, cartons, or non-rack goals.
failure_signature:
- Task10 W1 fired `wine_bottle_rack_wrong_object_handoff`, but recovery goals only
  included `wine_rack_1_main` placement and target-holding fallback.
- The rule trace recorded `bddl_goal_atoms = on(wine_bottle_1_main, wine_rack_1_top_region)`,
  yet `required_final_atoms` used `wine_rack_1_main`.
- W1 partial validation stopped after 3/3 failed episodes; the trigger was no longer
  the primary problem.
recovery_point: During cuTAMP recovery goal construction, rewrite wine-rack placement
  atoms to the explicit rack top region so full pick-and-place recovery is attempted
  before holding-only fallback.
applies_to:
  all:
  - task_language_matches: wine bottle.*rack|rack.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: wine_rack.*top_region|rack.*top_region
recovery_hints:
  params:
    grounding_profile: wine_rack_top_region_v1
    grounding_hints:
      placement_surface:
        grounding_profile: wine_rack_top_region_v1
        intent: top_support
        relation: true
        surface_name: wine_rack_1_top_region
    source: libero_goal_swap_task10_seed51_65_w2
evidence:
  tasks:
  - 'libero_goal_swap task10: put the wine bottle on the rack'
  - libero_90 task10 put the wine bottle on the rack
  episodes:
  - task10_seed51_w1_ep00
  - task10_seed52_w1_ep01
  - task10_seed53_w1_ep02
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
  - task10_ep5_seed56
  - task10_ep6_seed57
  - task10_ep7_seed58
  - task10_ep8_seed59
  - task10_ep9_seed60
  - task10_ep10_seed61
  - task10_ep11_seed62
  - task10_ep12_seed63
  - task10_ep13_seed64
  - task10_ep14_seed65
---
This hint owns only target binding. It does not change the trigger or the wine-bottle
grasp sampler.
