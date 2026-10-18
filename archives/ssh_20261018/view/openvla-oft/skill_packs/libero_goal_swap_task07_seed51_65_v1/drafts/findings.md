# Task07 W1 Findings

- Task: LIBERO-PRO goal-swap task07, `put the cream cheese in the bowl`.
- Baseline: 0/15 on seeds 51-65 with recovery disabled.
- Trace evidence: the target `cream_cheese_1_main` is effectively static in all inspected failures (`target_total_motion_m` around 6e-8 after q3).
- Intent evidence: most queries name `wine_bottle_1_main` as the intended object, with occasional `akita_black_bowl_1_main`; the intended object is not the target.
- Visual evidence: sampled frames show the cream-cheese box beside the bowl while the arm moves around the bottle/stove area.
- Proposed bundle: a narrow wrong-object repair entrypoint, a pack-local cream-cheese flat-box grasp profile, and bowl support grounding/geometry hints.
