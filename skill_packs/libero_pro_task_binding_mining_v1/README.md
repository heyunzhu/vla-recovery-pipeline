# LIBERO-Pro Task-Binding Mining v1

This isolated pack contains first-pass task-binding candidates mined from the 60 cached
LIBERO-Pro `goal/object/spatial × swap/task` contexts. The candidates use task language and
reset-time MuJoCo topology only. They do not use BDDL goal, region, init, or object-of-interest
fields.

The first pass intentionally covers only rules expressible by the current `on` / `inside`
profile schema: basket containment, stove cook-region placement, cabinet-top placement, and
wine-rack-top placement. Front-of relations, spatial disambiguation between duplicate bowls,
articulated open/close goals, switch goals, and compound goals remain unmatched until the
runtime schema is extended.

All candidates remain under `task_binding_fail_only` until offline admission and a later
runtime canary are accepted.
