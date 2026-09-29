# Bottom drawer articulation skill pack

This pack promotes the two evidence-backed lower-drawer execution profiles out
of runner-owned JSON and into the normal skill selection pipeline.

- One declarative skill admits the lower-drawer operation; the registry then
  selects a profile from current MuJoCo cabinet, handle and obstacle geometry.
- `profiles/articulation.yaml` owns MuJoCo bindings, handle-frame grasps and
  controller parameters.
- Generic articulation planning and execution remain in `tiptop_repro`.
- The original JSON configs remain supported as a no-skill fallback and as
  regression fixtures.

Selection uses normalized distance to successful geometry prototypes.  The
trace records measured features, per-profile scores and the nearest obstacle.
Missing, ambiguous or out-of-distribution geometry fails closed. Dataset,
suite and task IDs are not selector inputs.
