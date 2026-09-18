# Offline Mining Report

The v1 corpus contains 60 cached contexts from six LIBERO-Pro suites. Before mining, the
generic binder reported 15 successful bindings and 45 failures: 29 unsupported goal regions,
9 unresolved targets, 6 unsupported actions, and 1 parse failure.

Four reusable candidates were admitted over the complete 60-context corpus. They bind 27
contexts with zero selector failures or conflicts:

- basket containment: 20 contexts;
- cabinet top surface: 3 contexts;
- stove cook region: 2 contexts;
- wine-rack top region: 2 contexts.

Semantic review confirmed that every admitted target is the object named in the instruction,
every goal is the intended reset-time MuJoCo fixture or site, and every relation is `on` or
`inside` as stated by the language.

The remaining 33 contexts deliberately stay unmatched. They require capabilities not present
in the current profile schema: dynamic spatial selection between duplicate bowls, front-of
geometry, articulated drawer state, stove switch state, or compound goals. No task ID,
concrete instance, snapshot coordinate, or forbidden BDDL field was introduced to increase
coverage.
