# RGB-D recovery baseline audit

Audited on 2026-09-25 against `feature/bddl-language-and-goal` at
`326f4f7fe1d3f82f509e95d8d60e8c7a85c82ecb`. This is an implementation
inventory, not evidence that visual recovery already works.

## Confirmed runtime dependencies

| Entry | Current dependency | Required visual-mode change |
| --- | --- | --- |
| `skill_pipeline/runner.py::_get_libero_env` | Builds `OffScreenRenderEnv` without depth configuration | Enable only configured cameras and depth; capture synchronized RGB, depth, calibration and proprioception |
| `runner.py::_parse_episode_task` | Calls `read_scene(env, obs)` before task binding | Bind language against the visual scene; reject BDDL and MuJoCo goal sources in visual mode |
| `runner.py::_query_state` | Calls `read_scene` again for matcher features | Read the shared visual snapshot; represent missing predicates as unknown |
| `tiptop_repro/cutamp_controller_v2.py::CuTAMPV2OraclePerceiver.perceive` | Calls `read_scene` before symbolic scene and TAMP construction | Inject the same scene provider; keep oracle perceiver for the oracle mode |
| `tiptop_repro/libero_tiptop_executor.py::LiberoRobotClient.get_scene` | Calls `read_scene` during execution | Query the shared provider after each required observation |
| `tiptop_repro/geometry.py::estimate_object_geometry` | Consumes MuJoCo geometry or name-based proxies | Accept explicit visual geometry and reject missing geometry in visual mode |
| `tiptop_repro/task_parser.py::parse_task` | Supports `bddl` and `language_mujoco` | Add a separate language-and-visual-scene source |
| `skill_pipeline/task_binding_context.py` | Serializes MuJoCo objects, sites, geoms and nonrobot joints | Keep as oracle context; add a separate RGB-D context collector |

`scene_reader.py::read_scene` reads body poses, geoms, sites, nonrobot joints
and contacts. It must remain unreachable from visual decisions. Other legacy
controllers and executors also call it; inventory their actual dispatch before
claiming that a visual run is isolated.

## Success and `done` coupling

`runner.py::_check_task_success` accesses `env.check_success` for benchmark
scoring. That use belongs on the evaluation side only. The executor currently
copies `env.step(...).done` into `LiberoRobotClient.done` and uses it as positive
grasp, placement or recovery evidence at several sites, including the grasp
probe and operator execution. Visual mode must separate episode termination
from visual goal and holding evidence. Merely replacing `get_scene` would leave
this leak intact.

## First implementation slice

`skill_pipeline/rgbd_observation.py` now defines a replayable observation made
only of RGB, optical-Z depth in meters, a valid-pixel mask, intrinsics,
camera-to-world transform and JSON proprioception. It validates alignment and
calibration, saves lossless arrays, and back-projects valid pixels to world
coordinates. It accepts no simulator handle. `libero_rgbd_sensor.py` is the
sensor-only adapter for the installed robosuite 1.4.1; it reads camera
calibration, renderer depth and simulation time, and exports only whitelisted
robot proprioception. `collect_rgbd_snapshot.py` enables depth for one reset
snapshot without starting a policy episode.

This is a data contract, sensor adapter and offline geometry primitive. It
does **not** yet detect objects or switch the recovery runtime. Do not use its
existence to label a run RGB-D recovery.

## First server snapshot

The installed 5880 environment was checked directly: Python 3.8,
robosuite 1.4.1, `IMAGE_CONVENTION="opengl"`. The installed camera utility
converts normalized depth using the simulator near/far planes. The LIBERO
wrapper accepts `camera_depths=True`. RGB and depth are sampled in one camera
observable; the adapter flips both vertically into top-left pixel convention.

On 2026-09-25, a reset-only CPU capture completed for `libero_spatial`
task 0, init 0, seed 7, `agentview` 128 × 128. All 16,384 pixels had finite
depth. The original pixel-index back-projection estimated a central table
patch near 0.904 m. Switching to actual pixel centers (`index + 0.5`) reduced
the same patch's median to 0.9017 m. An independent evaluation-only simulator
check measured the table box top at 0.9000 m. The median absolute difference
over 1,644 selected table pixels is 1.7 mm. The robot end-effector projects
near pixel `(62, 30)` at camera Z 0.950 m; the image preview is consistent
with the visible robot. This supports the depth scale and camera convention
for the first fixed view, but is not a full calibration benchmark.

A second reset with both `agentview` and `robot0_eye_in_hand` succeeded. Both
frames have the same step and timestamp. The `agentview` RGB/depth arrays are
bit-identical to the single-camera capture, and the wrist view has its own
extrinsic. A three-step simulated wrist motion probe advanced time from 0 to
0.15 s and changed the wrist-camera translation by 5.9 mm while end-effector
translation changed by 3.9 mm. Their 2.0 mm vector difference is plausible
for an offset camera during rotation; the key check is that a fresh frame
received a fresh extrinsic, with all depth pixels valid. This is a sensor
diagnostic, not a recovery rollout.

Accepted schema-v2 server artifact:
`/mnt/sdb/24_yyx/demo/rgbd-spatial-task0-init0-20260925-v2`.
Dual-camera server artifact:
`/mnt/sdb/24_yyx/demo/rgbd-spatial-task0-init0-dualcam-20260925`.
Local copies are under `D:\大三上\科研\rgbd_spatial_task0_init0_20260925_v2`
and `D:\大三上\科研\rgbd_spatial_task0_init0_dualcam_20260925`.

The first offline visual-geometry pass fitted an **unnamed plane candidate**
from the saved `agentview` frame using a declared workspace box
`x=[-0.6,0.3], y=[-0.6,0.6], z=[0.7,1.2]` m. It found 7,381 inlier points,
height at world origin 0.9018 m, upward normal Z 0.999999 and 0.53 mm RMS
fit residual. Its measured XY extent is only a visible bounding box; it is
**not** a semantic table label or verified free placement region. The JSON
artifact is `agentview/plane_candidate.json` in the local schema-v2 snapshot.

Validation: the new observation/sensor/geometry/scene tests pass, and
the complete local skill-pipeline test suite passes (535 tests) when Windows
`TEMP`/`TMP` point to the long-form D: workspace path. With the host's
default short-form temp path, one existing path-string comparison fails on
Windows despite referring to the same file; no production code depends on
that comparison. The server's Python 3.8 syntax check and reset capture pass.

## 2026-09-28: object proposal and scene interface progress

A second reset-only `agentview` snapshot at 512 × 512 was captured for the
same `libero_spatial` task 0 / init 0 / seed 7. This higher resolution is for
recovery perception; the VLA image pipeline has not been changed. The artifact
is `/mnt/sdb/24_yyx/demo/rgbd-spatial-task0-init0-512-20260928` on the 5880
server and `D:\大三上\科研\rgbd_spatial_task0_init0_512_20260928` locally.

Depth-only foreground extraction produced seven **unnamed** components. The
mask overlay and `visual_scene.json` are in the local artifact's
`agentview/proposals/` directory. A nearby bowl and ramekin occupy one
connected component, so the components cannot be treated as semantic objects
or used to bind this task's target. This is an observed failure of the simple
geometric proposal baseline, not a reason to read simulator instance IDs.

`rgbd_scene.py` now accepts masks from a declared visual source, lifts valid
depth into visible world-space bounds and tracks categorized detections across
steps. It leaves height-only proposals unbound, retains missing tracks as
`not_observed`, marks close identity matches `ambiguous`, and rejects substantial
mask overlap. Its coordinates are visible-surface geometry, not MuJoCo body
origins. The module accepts no simulator handle. The tracker has only been
verified with synthetic mask sequences; there is not yet a text-guided model
producing masks for real frames.

## Next gate: semantic target and shared provider

1. Freeze and test a text-guided detection/segmentation backend on a small
   set of cached 512 × 512 frames. It must separate the two black bowls,
   ramekin and plate and report uncertainty when it cannot. Keep every
   same-category instance; do not turn detector scores into calibrated
   probabilities without measurement.
2. Bind the language relation to a stable visual object ID and derive a
   verified placement region from visible support geometry. The current plane
   bounding box alone is not a free placement region.
3. Connect runner, controller and executor to one visual scene provider, with
   explicit unknown handling and a separate evaluation-only success signal.

Robosuite documents image/depth observables and normalized renderer depth in
its current documentation. Its camera utilities include intrinsic, extrinsic
and depth conversion helpers. The installed simulation version must be checked
before applying those helpers or their image convention:

- https://robosuite.ai/docs/modules/sensors.html
- https://robosuite.ai/docs/modules/renderers.html
- https://github.com/ARISE-Initiative/robosuite/blob/master/robosuite/utils/camera_utils.py
