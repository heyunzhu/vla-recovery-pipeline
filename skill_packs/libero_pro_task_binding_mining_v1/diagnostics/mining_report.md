# Offline Mining Report

The v1 corpus contains 60 cached contexts from six LIBERO-Pro suites. Before mining, the
generic binder reported 15 successful bindings and 45 failures: 29 unsupported goal regions,
9 unresolved targets, 6 unsupported actions, and 1 parse failure.

Eleven reusable candidates were admitted over the complete 60-context corpus. They bind 55
contexts with zero selector failures or conflicts:

- basket containment: 20 contexts;
- duplicate-black-bowl spatial selection and plate placement: 20 contexts;
- cabinet top surface: 3 contexts;
- stove cook region: 2 contexts;
- wine-rack top region: 2 contexts;
- stove-front virtual table region: 2 contexts;
- cabinet open state: 2 contexts;
- open-top-cabinet then place inside: 2 contexts;
- stove on/off state: 2 contexts.

Semantic review confirmed that every admitted target is the object named in the instruction
and every goal or state entity is selected from the reset-time MuJoCo scene. The stove-front
region is derived from the cook-region-to-button direction and is materialized in the current
planner frame; it does not copy a BDDL rectangle or snapshot coordinate.

The five contexts unmatched by this pack are ordinary unique-object placements already
handled by the generic language + MuJoCo binder. Together, the generic binder and this pack
therefore provide semantic bindings for all 60 contexts.

The six action-bearing contexts are explicitly marked `semantics_only`: their language goals
are bound without BDDL, but articulated drawer and stove-switch execution is not implemented
by this mining pass. The other 49 skill matches are planner-ready placement bindings. No task
ID, concrete instance, snapshot coordinate, or forbidden BDDL field was introduced to
increase coverage.
