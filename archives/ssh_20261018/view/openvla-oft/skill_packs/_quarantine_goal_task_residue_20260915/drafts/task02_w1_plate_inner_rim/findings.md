# Task02 W1 Findings

Task: `libero_goal_task` task02, language `Put the plate on the stove`.

Baseline seed51-65 is 0/15 with skills disabled. W0 with the inherited pack is 1/15. The W0 traces show that the two inherited task02 repair entrypoints fire, so the primary miss is not trigger recall.

The inherited pack already supplies `ground_plate_stove_cook_region` and `geometry_stove_cook_region_surface`; representative serialized cuTAMP problems confirm the goal surface is `flat_stove_1_cook_region` and `real_cutamp_grasp_dof` is 6. Remaining failures are dominated by no satisfying particles, motion-planning failures, and occasional close/lift checks that report `gripper_closed_but_not_holding` or `lift_probe_unconfirmed`.

The W1 draft adds `plate_inner_rim_topdown_v2`, a pack-local plate grasp profile that samples nearer the inner rim and tries tangential yaw candidates before radial yaws. It intentionally reuses the existing repair entrypoints, stove grounding, and stove geometry so the validation isolates the grasp change.
