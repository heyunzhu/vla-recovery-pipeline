# W2 Findings

Task: libero_goal_swap task07, put the cream cheese in the bowl.

W1 reproduced the archived intermediate result: 6/15 successes with the wrong-object trigger and cream-cheese grasp/grounding/geometry bundle active. The scorer triage points at 	rajectory_tracking_budget_exhausted, mostly during place_hover, with additional failures from a too-strict post-grasp lift/release-height guard.

The W2 candidate keeps the W1 entrypoint unchanged and adds only a pack-local place profile. The profile gives the final cream-cheese-to-bowl place stage more lift/hover/drop budget and accepts the slightly high release pose observed over the bowl.
