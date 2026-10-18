---
id: cream_cheese_task07_flat_box_topdown_deep
name: Task10 hybrid using task07 cream-cheese flat-box grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 90
when_to_apply: Diagnostic hybrid run for task10 rack placement when recovery manipulates
  cream_cheese_1_main.
when_not_to_apply: Do not use outside this temporary task10 hybrid experiment.
failure_signature:
- Forced q5 and W1-W3 task10 recoveries used the generic `topdown_proxy` sampler
  and failed before executable pick planning.
- Task07 showed the cream-cheese flat-box top-down deep profile can produce executable
  Pick trajectories for the same target object class.
recovery_point: After the task10 repair trigger has selected recovery for cream cheese
  and the rack top grounding/geometry hints have been merged.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: '*cream_cheese*'
recovery_hints:
  grasp_profile: cream_cheese_flat_box_topdown_deep_v1
  target: target
  params:
    source: task10_hybrid_task07_grasp_experiment
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - 'libero_goal_swap task07: put the cream cheese in the bowl'
---
This is a controlled experiment: keep task10 rack grounding/geometry and reuse only
the task07 cream-cheese flat-box grasp profile.
