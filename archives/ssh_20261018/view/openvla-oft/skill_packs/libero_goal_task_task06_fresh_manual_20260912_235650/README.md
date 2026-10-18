# LIBERO goal task06 fresh manual pack

Fresh empty scratch skill pack for manual mining of `libero_goal_task` task06, `Push the cream cheese to the front of the stove`.

## Status

This pack admits only two recovery hints:

- `task06_stove_front_bddl_region_grounding_v1` keeps the goal surface on the BDDL table region `main_table_stove_front_region` instead of the parser fallback `flat_stove_1_main`.
- `task06_stove_front_bddl_table_rect_geometry_v1` registers that BDDL region as a virtual fixed table rectangle for recovery planning.

No repair trigger is admitted. Forced-recovery diagnostics showed that the grounding/geometry correction works, but the available cuTAMP recovery backend still tries to solve this push task through a pick/place skeleton and does not produce an executable plan. See `diagnostics/task06_mining_findings.md`.
