# Bottom drawer articulation skill pack

This pack promotes the two evidence-backed lower-drawer execution profiles out
of runner-owned JSON and into the normal skill selection pipeline.

- Skills decide when a profile applies.
- `profiles/articulation.yaml` owns MuJoCo bindings, handle-frame grasps and
  controller parameters.
- Generic articulation planning and execution remain in `tiptop_repro`.
- The original JSON configs remain supported as a no-skill fallback and as
  regression fixtures.

The current suite guards are deliberately conservative admission boundaries.
They must be replaced by geometry/contact diagnostics only after those
diagnostics have cross-suite validation evidence.
