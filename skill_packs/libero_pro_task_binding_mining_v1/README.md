# LIBERO-Pro Task-Binding Mining v1

This isolated pack contains first-pass task-binding candidates mined from the 60 cached
LIBERO-Pro `goal/object/spatial × swap/task` contexts. The candidates use task language and
reset-time MuJoCo topology only. They do not use BDDL goal, region, init, or object-of-interest
fields.

The admitted rules cover basket containment, stove cook-region placement, cabinet-top
placement, wine-rack-top placement, and reset-time spatial disambiguation between duplicate
black bowls. The spatial selector first uses the strict generic binder, then ranks only
language-matched candidates against current MuJoCo objects, fixture sites, or the table
center. Front-of relations, articulated open/close goals, switch goals, and compound goals
remain unmatched until the runtime schema is extended.

All candidates remain under `task_binding_fail_only` until offline admission and a later
runtime canary are accepted.
