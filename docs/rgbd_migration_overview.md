# RGB-D migration: repository entry point

Updated: 2026-10-07. Branch: `feature/rgbd-recovery`.

## Purpose and current status

Replace MuJoCo object ground truth in recovery with observations from RGB-D,
while retaining the existing skill, cuTAMP, and execution interfaces. Robot
proprioception remains an explicit input. Simulator object truth must not serve
as a fallback in the visual recovery path.

The visual observation, detection, shared scene, geometry export, and native
planner input paths have been exercised. The real GPU planner runs but rejects
the initial collision state. No executable recovery trajectory, online RGB-D
recovery success, or completed skills-off/oracle/RGB-D comparison is claimed.
Experiments are paused while this repository is prepared for GitHub submission.

## Code map

| Area | Entry points |
| --- | --- |
| Observation and scene | `experiments/robot/libero/skill_pipeline/rgbd_observation.py`, `rgbd_scene_provider.py` |
| Shared planning evidence | `experiments/robot/libero/skill_pipeline/visual_planning_input.py` |
| Visual TAMP geometry | `experiments/robot/libero/skill_pipeline/visual_tamp_adapter.py` |
| Native world and backend | `experiments/robot/libero/tiptop_repro/visual_cutamp_world.py`, `real_cutamp_backend.py` |
| Export and probes | `scripts/recovery/skill_pipeline/build_visual_tamp_problem.py`, `probe_native_visual_planner.py`, `probe_native_initial_collision.py` |
| Candidate visual skill pack | `skill_packs/rgbd_bowl_rim_candidate_v1/` (candidate, not validated online) |
| Unit tests | `experiments/robot/libero/skill_pipeline/tests/` |

## Verified evidence

- Native CPU input contains one movable and 1,809 static obstacles, including
  the goal surface. Observed residual geometry is retained.
- Explicit visual pad-model inference can provide an initial HandEmpty fact;
  this is an inference under stated assumptions, not physical confirmation.
- First GPU planner run: no feasible solution; initial object collision cost
  approximately 0.502.
- Subsequent collision attribution saved a different set of 50 native spheres:
  total cost approximately 0.582, with 47 positive-cost obstacles. These spheres
  sample the target's whole AABB, including surfaces not measured by RGB-D.
- Native hand position error approximately 0.50 mm; tool-to-measured-grip-site
  error approximately 8.50 mm. Base alignment is conditional on static FK and
  proprioception, not an independently verified extrinsic calibration.

Details: [native collision attribution](rgbd_native_collision_attribution_20261007.md),
[visual TAMP input](rgbd_visual_tamp_problem_20261007.md), and
[chronological project status](rgbd_recovery_project_status_20260928.md).

## Latest geometry option

The exporter now accepts `--voxel-shape occupied_point_bounds`. It preserves the
same occupied bins and encloses each bin's observed points exactly, with no
outward margin, instead of filling the complete voxel cell. The default remains
`full_cell` for reproducible comparison. Exceeding the obstacle budget raises
an error; obstacles are not silently discarded. Hidden geometry remains
unknown. This option has unit coverage but has not yet been verified by a new
native GPU run. Semantic object boxes are the exact min and max of the visible
points, also with no outward margin.

## Checks and reproduction

Install the project dependencies in a personal environment. The core suite is:

Submission check on 2026-10-07: 796 tests completed successfully (one skipped),
including 11 focused adapter/geometry tests. These are software checks, not
robotic task success measurements.

```sh
python -m unittest discover -s experiments/robot/libero/skill_pipeline/tests -p 'test_*.py'
python scripts/recovery/skill_pipeline/build_visual_tamp_problem.py --help
python scripts/recovery/skill_pipeline/probe_native_initial_collision.py --help
```

Captured frames, detector model weights, vendor repositories, environments,
full planner results, and server logs are external inputs. Documentation may
record original local paths as provenance; those paths are not portable runtime
defaults. Supply your own input paths through the CLIs. The native planner needs
the separately installed cuTAMP/cuRobo CUDA environment; unit tests alone do not
verify GPU execution or recovery success.

## Remaining acceptance work

2026-10-09 update: the controlled wine-bottle-on-plate recovery anchor completed
all four staged replacements: proprioceptive initial hand state, RGB-D collision
geometry, current RGB-D object tracking during execution, and visual instance
IDs without simulator body association. Recovery succeeded in 154 environment
steps with simulator reward/done hidden from the control loop; the independent
final simulator evaluation also succeeded. This is one recovery replay with
explicit bottle/plate assumptions, not an end-to-end VLA rollout or a general
benchmark result. See [experiment record](rgbd_recovery_proprio_and_execution_20261009.md)
for failures, evidence locations, and remaining scope. The acceptance list below
still applies to the general pipeline.

1. Compare observed-point bounds using the same saved collision spheres.
2. Ground semantic obstacle and dynamic collision geometry in measured surfaces.
3. Align the native tool and gripper model; obtain a checked executable plan.
4. Run the visual pick/place loop with post-action visual verification.
5. Validate the candidate skill pack and run matched skills-off/oracle/RGB-D
   trials, then held-out and failure tests required by the migration plan.

## Repository hygiene

Keep reusable code in the existing runtime directories, launchers in `scripts/`,
and benchmark assets in independent `skill_packs/`. Selected audit reports and
figures in `docs/` are retained as evidence. Bulk experiment artifacts, videos,
private keys, credentials, model weights, datasets, and environments belong
outside Git. See [repository layout](repository_layout.md).
