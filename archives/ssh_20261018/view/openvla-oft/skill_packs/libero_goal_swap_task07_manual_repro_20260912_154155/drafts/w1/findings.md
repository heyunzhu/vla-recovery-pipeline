# W1 Findings

Task: `libero_goal_swap` task07, `put the cream cheese in the bowl`.

The empty-pack baseline fail set contains 15/15 failures. Across the extracted query records the target `cream_cheese_1_main` stays effectively static, while intent is overwhelmingly assigned to `wine_bottle_1_main` and occasionally `akita_black_bowl_1_main`. Every failed episode has a legal wrong-object handoff window with an empty hand, open aperture, non-target intent, target distance below 0.37 m, target future XY separation above 0.18 m, and wrong-object margin above 0.10 m.

The W1 candidate therefore adds a narrow fail-only handoff trigger plus task-local cream-cheese flat-box grasp sampling and bowl support grounding/geometry. The change is pack-local only: no runner, planner, global skill library, or LIBERO assets are changed.
