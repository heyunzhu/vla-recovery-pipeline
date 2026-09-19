---
id: grasp_cream_cheese_bowl_flat_box_topdown_deep
name: Cream cheese bowl flat-box deep top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 55
when_to_apply: When recovery is manipulating a cream cheese box and the baseline VLA
  never picked the target object.
when_not_to_apply: Do not use for bowls, mugs, bottles, cans, tall cartons, books,
  baskets, trays, or non-flat-box objects.
failure_signature:
- The task07 target is `cream_cheese_1_main`, a thin rectangular grocery box next
  to the bowl.
- Baseline traces show no target motion across 15 failures, so recovery must generate
  the pick from geometry rather than inherit a VLA grasp.
recovery_point: After a repair skill has entered `cutamp_recover`, bias cuTAMP to
  top-down side grasps that close into the box body.
applies_to:
  all:
  - task_language_matches: cream cheese.*bowl|bowl.*cream cheese
  - target_name_matches: cream_cheese|cream cheese
  - target_name_excludes: butter|chocolate_pudding|book|bowl|mug|can|bottle|milk|orange_juice
recovery_hints:
  grasp_profile: cream_cheese_flat_box_topdown_deep_v1
  target: target
  params:
    source: libero_goal_swap_task07_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task07: put the cream cheese in the bowl'
  - libero_90 task07 put the cream cheese in the bowl
  episodes:
  - task07_seed51_ep00
  - task07_seed53_ep02
  - task07_seed57_ep06
  - task07_seed58_ep07
  - task7_ep0_seed51
  - task7_ep1_seed52
  - task7_ep2_seed53
  - task7_ep3_seed54
  - task7_ep4_seed55
  - task7_ep5_seed56
  - task7_ep6_seed57
  - task7_ep7_seed58
  - task7_ep8_seed59
  - task7_ep9_seed60
  - task7_ep10_seed61
  - task7_ep11_seed62
  - task7_ep12_seed63
  - task7_ep13_seed64
  - task7_ep14_seed65
---
This hint owns only the target-object pick sampler. It keeps the new
cream-cheese profile inside this scratch pack so it cannot accidentally activate
the older LIBERO-90 flat-box skills.
