# libero_goal task1 ("open the bottom drawer of the cabinet"): can the current skill solve it?

**Answer: no.** The articulation skill is reached and binds correctly, but the planner is infeasible
at the very first step in 5/5 episodes, so no approach/articulate/retreat motion is ever executed and
the drawer never opens (confirmed from video, not from `success` flags).

## Task identity (an old note of ours was misleading)

`libero_goal_task` task1 loads
`.../bddl_files/libero_goal_task/open_the_middle_drawer_of_the_cabinet.bddl`, but the **live goal atom
is the bottom drawer** and the suite language matches:

```
language      : open the bottom drawer of the cabinet
bddl_goal_atoms: [{"predicate": "open", "args": ["wooden_cabinet_1_bottom_region"]}]
```

So the earlier artifact line "Open the middle layer of the drawer" came from the *file name*, not the
goal. The teammate's statement (t1 = open the bottom drawer) is correct. `docs/libero_goal_task10_cross_suite_mining_2026-09-16.md:134`
also recorded t1 as a blocker for exactly this reason: "executor lacks an `open` primitive for
articulated drawers" — that is the gap the ported articulation skill was meant to close. It closes it
for the **top** drawer, not for the **bottom** one.

## Run and result

Recipe = the verified task8 recipe (seed 90, `episode_seed_start 0`, `--force_recovery_query 0`,
`--max_recovery_calls 1 --max_replans 0 --max_recovery_steps 600`, `--save_video`), with a binding set
filtered down to the wooden cabinet's bottom drawer
(`wooden_cabinet_1_cabinet_bottom` / joint `wooden_cabinet_1_bottom_level` / handle `wooden_cabinet_1_g40`,
`open_range [-0.155,-0.145]`, top-down grasp offset 0.0965 m).

Run root: `$SSD/goal_task1_bottom_5ep_20260927` (SSD = `/inspire/ssd/project/feelingai/chenwenming-25012/jxs/xinghanbo`).

| episode | success | queries | steps | video |
| --- | --- | ---: | ---: | --- |
| ep00-ep04 | False (0/5) | 61 | 300 | yes |

Every episode, per `recovery_trace.jsonl` (identical in all five):

```json
{"kind": "plan", "label": "real_cutamp_no_feasible_goal", "query_idx": 0, "success": false,
 "error": "ArticulationError:no_feasible_articulated_plan:['curobo_free_motion_failed:MotionGenStatus.IK_FAIL']",
 "num_satisfying": 0}
```

The goal reaching the solver is already the resolved one and looks right:

```json
"goal_atoms": [{"predicate": "open", "args": ["wooden_cabinet_1_cabinet_bottom"]},
               {"predicate": "handempty", "args": []}]
"articulations": {"wooden_cabinet_1_cabinet_bottom": {"joint_name": "wooden_cabinet_1_bottom_level",
                  "joint_type": "slide", "axis": [0,-1,0], "anchor": [0.6816, -0.2339, -0.007],
                  "reference_position": 0.0, "joint_range": [-0.16, ...]}}
```

Notes on the failure:

- `--force_recovery_query 0` means "enter recovery at query 0" (`runner.py:1799`), so the recovery was
  attempted from the **clean initial state** (video frame 0: arm at home) — the same timing at which
  task8 succeeds. A jammed VLA terminal pose is therefore *not* the cause.
- The error is on **free motion** (`curobo_free_motion_failed`), i.e. cuRobo's IK for the pre-grasp
  pose, **not** a collision (`MotionGenStatus.IK_FAIL`, versus task04's
  `INVALID_START_STATE_WORLD_COLLISION`).
- No `articulation:approach/articulate/retreat` rows exist at all, so the failure precedes execution.
- After the failed recovery the VLA runs out its full budget (61 queries x 5 = 300 steps) and also
  fails; the video shows the arm reaching to the cabinet's lower front and returning home with the
  drawer still closed.

## Control: it is the bottom drawer, not the libero_goal scene

libero_90 task7 is the **same language** ("open the bottom drawer of the cabinet"), the **same
KITCHEN_SCENE1 wooden cabinet** in which task8 (top drawer) succeeded 5/5 with this same skill, and
the same bottom binding. Run root `$SSD/task7_bottom_5ep_20260927`:

| episode | success | queries | steps | plan error |
| --- | --- | ---: | ---: | --- |
| ep00 | False | 81 | 400 | `...IK_FAIL`, `num_satisfying: 0` |
| ep01 | **True** | 37 | 179 | `...IK_FAIL`, `num_satisfying: 0` |
| ep02-ep04 | False | 81 | 400 | `...IK_FAIL`, `num_satisfying: 0` |

- The skill fails with the **identical** error string in this second scene too (5/5), and again
  contributes **zero** execution rows.
- The single `success=True` (ep01) came from the **VLA policy**, not the skill: the episode ends at
  179 steps with the recovery already failed, and the video shows the bottom drawer pulled out. This
  is a VLA capability point, not a skill result.
- Top drawer (task8) = 5/5 via the skill; bottom drawer (task1 and task7) = 0/10 via the skill.

**Conclusion**: the blocker is the bottom-drawer target geometry — the pre-grasp pose for the bottom
handle is not IK-reachable for cuRobo's free-motion planner — and it is independent of the
`libero_goal` scene. The same binding file works for the top drawer, whose only difference is the
handle height/anchor.

## Root cause: what `IK_FAIL` is, and why it happens here

### Where it is raised (source-verified)

`cutamp_articulation.solve` (line ~127) computes the tool pose as
`target = part.handle_pose(reference_position) @ grasp` and calls `motion.approach(q_init, target, s)`.
`CuroboArticulationMotion.approach` (`articulation_curobo.py:132`) moves the pose **5 cm back along the
gripper's z axis** and calls `MotionGen.plan_single(timeout=2.0, enable_finetune_trajopt=False)`;
a failed result raises `curobo_free_motion_failed:{status}`.

cuRobo (`third_party/curobo/src/curobo/wrap/reacher/motion_gen.py`) defines

```python
#: Inverse kinematics failed to find a solution.
IK_FAIL = "IK Fail"
```

and sets it in `plan_single` **before** any planning:

```python
ik_result = self._solve_ik_from_solve_state(goal_pose, solve_state, start_state, ...)  # -> ik_solver.solve_any
ik_success = torch.count_nonzero(ik_result.success)
if ik_success == 0:
    result.status = MotionGenStatus.IK_FAIL
    return result          # graph search and trajopt never run
```

So `IK_FAIL` means: **zero IK solutions were found for the requested tool pose** — cuRobo returned
early and never attempted graph search or trajectory optimization. It is *not* the start-state
collision status (that is `INVALID_START_STATE_WORLD_COLLISION`, seen on task04) and *not* a planning
failure (`GRAPH_FAIL`/`TRAJOPT_FAIL`). Because the IK solver runs against the loaded world, "a
solution" also has to be collision-free — hence the probe below separates the two causes.

### Probe (`scripts/recovery/skill_pipeline/probe_articulation_ik.py`)

Replays the saved `*.problem.json` through the identical objects (`_load_problem` ->
`ArticulatedPart` -> `CuroboArticulationMotion`) and re-asks the same question under ablations. It
**reproduces `curobo_free_motion_failed:MotionGenStatus.IK_FAIL` exactly** on the failing problem, so
the reproduction is faithful.

| variant | bottom drawer (task1, failed) | top drawer (task8, succeeded) |
| --- | --- | --- |
| `plan_single(pre)` with the collision world | **IK_FAIL** | ok (43 pts) |
| `solve_ik(pre)` with the collision world | **no solution** | solution found |
| `plan_single(pre)` with the world **emptied** | **IK_FAIL** | ok (44 pts) |
| `solve_ik(pre)` with the world **emptied** | **no solution** | solution found |
| standoff 0.02 / 0.05 / 0.08 / 0.12 / 0.18 m | all **IK_FAIL** | all ok |
| goal raised by -0.03 / 0.00 / +0.03 / +0.06 m | all **IK_FAIL** | all ok |
| goal raised by **+0.10 m** | **ok (47 pts)** | ok |

Requested poses (both are horizontal, front-facing approaches, i.e. the gripper z axis is world -y):

| | handle xyz | `pre` (grasp - 5 cm) | approach dir | table top |
| --- | --- | --- | --- | --- |
| bottom | (0.6844, -0.1322, **0.0341**) | (0.6844, 0.0143, 0.0341) | (0, -1, 0) | -0.03 |
| top | (0.6693, -0.1983, **0.1769**) | (0.6693, -0.0518, 0.1769) | (0, -1, 0) | -0.03 |

`q_init` is the LIBERO rest pose in both cases (FK ≈ (0.457, 0.000, 0.358)).

### Conclusion

- The bottom drawer's failure is a **kinematic reachability limit, not a collision**: emptying the
  entire collision world (139 boxes) leaves the IK stage with zero solutions, and the standoff along
  the approach axis is irrelevant (0.02-0.18 m all fail).
- It is **height-specific**: the very same pose 10 cm higher is solvable. The bottom handle sits at
  z = 0.034, only ~6 cm above the table top, with the tool centre required to be at that same height
  because the configured grasp is a horizontal front-facing grasp. The top handle at z = 0.177 is
  comfortably inside the workspace (every variant succeeds).
- Practical implication: the fix is the **grasp pose**, not the planner budget. A top-down or
  downward-tilted grasp for the low drawer puts the tool centre above the handle - in the band the
  probe shows is reachable (about +0.10 m) - instead of demanding a horizontal wrist at table height.

Probe reports kept at `E:\VLA_recovery_workspace\articulation_ik_probe_20260927\{bottom,top}.json`.

### Confirmed with the existing attribution tools

`diagnose_cutamp_recovery_failures.py --run-dir $SSD/goal_task1_bottom_5ep_20260927 --task-id 1`:

- episodes 5, feasible 0, infeasible 5; every problem carries
  `reason=ArticulationError:no_feasible_articulated_plan:['curobo_free_motion_failed:MotionGenStatus.IK_FAIL']`
  (elapsed 11-16 s)
- **final blockers: none; zero-satisfying constraints: none; world collision candidates: `[]`**;
  phase guess `unknown_goal_optimization`
- i.e. there is **no cuTAMP constraint-level blocker to attribute**: the failure is raised inside the
  articulation backend, before the pick/place constraint optimization ever runs.

`collision_attribution_probe.py --solve-json <bottom problem> --q <q_init> --verify` (135 obstacles):

- worst depth at `q_init` = **-0.072 m**, on `wine_rack_1_main__mj_geom_229`; every ranked entry is
  negative, and `sphere_obb_penetration` is "positive when the sphere penetrates the box; negative is
  the clearance" (`collision_report.py:50`). So the start state **touches nothing** (nearest obstacle
  7.2 cm away).
- cuRobo's aggregate collision cost at that configuration is **0.00000** - collision-free. This is
  exactly why the status is `IK_FAIL` and not `INVALID_START_STATE_WORLD_COLLISION`.

Tool gap found: the same probe **cannot sweep an articulation plan** -
`--result-json <task8 solve_*.result.json>` returns
`no q0/q1/... waypoints in optimized_plan.bindings`, because articulation results are stored as
`executable_plan[].plan.actions[].positions` (approach/articulate/retreat), not in the pick/place
`optimized_plan.bindings` shape. Teaching `extract_waypoints` about articulation plans would let the
existing tool name obstacles per leg for the cases that *do* plan.

Reports kept at `E:\VLA_recovery_workspace\attribution_20260927\{diagnose.md,diagnose.json,bottom_qinit.json}`.

### Is the requested pose even correct? (handle audit)

`handle_reference` equals the **handle bar geom** exactly (`g40` bottom / `g18` top: half extents
[0.0077, 0.0082, 0.0444] = an 8.9 cm tall bar; `g41/g42` are its two 1.1 cm brackets), with an
identical rotation matrix in both cases. So the pose is built from the real handle, not from a
fallback site or the drawer front panel.

The 6.6 cm y difference between the two scenes is **scene placement, not a bug**: the cabinet body
(`wooden_cabinet_1_main`) sits at y = -0.250 in the libero_goal t1 scene and y = -0.316 in
KITCHEN_SCENE1, and the handle-to-cabinet offset is 0.118 m in both.

### Which part of the pose is infeasible? (orientation sweep)

Same handle, same standoff (0.0965 m), tool centre placed at `handle_center - approach * standoff`:

| approach | bottom (task1) | top (task8) | tool centre (bottom) |
| --- | --- | --- | --- |
| front-horizontal `(0,-1,0)` - **the configured grasp** | **IK_FAIL** | ok | (0.6844, -0.0357, 0.0341) |
| top-down `(0,0,-1)` | **IK_FAIL** | ok | (0.6844, -0.1322, 0.1305) |
| tilt 45 deg `(0,-1,-1)/sqrt2` | **ok** | ok | (0.6844, -0.0640, 0.1023) |
| tilt 30 deg `(0,-0.866,-0.5)` | **ok** | ok | (0.6844, -0.0486, 0.0824) |

So the bottom drawer is *not* unreachable in general - it is unreachable **for this grasp**: the
configured horizontal approach puts the tool centre exactly at the handle's own height (z = 0.034,
about 6 cm above the table top), and that pose has no joint solution from this robot base, while the
same handle reached from 30-45 degrees below succeeds. Note top-down alone does **not** fix it either.

## Tilted-grasp attempt: pre-flight rejected every candidate (no episode was run)

`scripts/recovery/skill_pipeline/choose_tilted_grasp.py` rebuilds the recorded problem with a
candidate grasp and runs the **full** `cutamp_articulation.solve`, so the decision costs no episode.
The new grasp would have gone into a **new** file
(`$SSD/articulation_drawer_bottom_tilt.json`); the top-drawer config and every repo file were only
read, and the run was aborted before any eval because nothing solved.

| candidate | tool centre | approach | full solve |
| --- | --- | --- | --- |
| `rz45` | (0.6844, -0.0640, 0.1024) | (0, -0.707, -0.707) | free motion `IK_FAIL` |
| `probe45` | same | same | **approach passes**, then `articulation_ik_failed` |
| `rz30` | (0.6844, -0.0487, 0.0824) | (0, -0.866, -0.5) | free motion `IK_FAIL` |
| `probe30` | same | same | **approach passes**, then `articulation_ik_failed` |
| horizontal (configured) | (0.6844, -0.0357, 0.0341) | (0, -1, 0) | free motion `IK_FAIL` |

`rz*` and `probe*` share the tool centre and approach and differ only in the **roll about the approach
axis** (90 deg apart) - and the roll decides whether the approach is solvable at all.

### The real blocker is the slide, not the approach

`probe_articulation_refine.py` walks the slide exactly as `refine_articulation` does (one seed per
step, `slide_step` = 5 mm, 31 steps to -0.15 m):

| candidate | grasp pose IK | slide | first failure | other seeds / multi-seed planner |
| --- | --- | --- | --- | --- |
| `probe45` | ok | **22 / 31** | s = **-0.115 m** | three seeds fail **and** `plan_single` `IK_FAIL` |
| `probe30` | ok | 7 / 31 | s = -0.04 m | `plan_single` `INVALID_START_STATE_WORLD_COLLISION` |
| `rz45` | fails | - | - | cannot even grasp |

So `articulation_ik_failed` is **not** a single-seed artifact - other seeds and the multi-seed planner
fail on the same pose. The drawer is pulled 11.5 cm of the required >= 14.5 cm (`open_range`
[-0.155, -0.145]) and then the fixed grasp becomes unsolvable (the drawer slides *towards* the robot,
so the wrist runs out of configuration at the end of the travel).

A roll sweep at tilt 45 deg (`--rolls 0,30,-30,60,-60,90`) shows the feasible roll is essentially a
single point: only roll 0 gets in at all (22/31 steps, 0.115 m); every other roll cannot even solve
the grasp pose. `reached_open_range` is false for all of them.

**Corrected conclusion**: changing the grasp pose is necessary but *not sufficient* for the low
bottom drawer. A tilted grasp fixes the approach and buys 77% of the pull; the last ~3 cm are
infeasible while one fixed grasp transform must be held for the whole slide. Options from here:
re-grasp mid-travel (a second GraspHandle after a partial pull - a real change to the articulation
domain, needing a task8 regression), grasp a different point on the 8.9 cm-tall bar, or allow the
wrist to re-orient while keeping contact.

### Rollback verified (nothing was left behind)

`md5sum` before and after the attempt, plus the absence of the temp config and of any eval directory:

```
articulation_drawer_top.json                  832376aebcee0b17abc190865274870a   (unchanged)
articulation_drawer_bottom.json               5da3c3bdd3a117d1dcc6971375a6fae0   (unchanged)
libero90_drawer_articulation_language.json    78632a6a567c647c0ed15f26a34219c2   (unchanged)
articulation_drawer_bottom_tilt.json          does not exist
tilt_*_20260927/eval/...                      no eval directories created
```

Only inert helper scripts were uploaded into the server repo's `scripts/recovery/skill_pipeline/`
(`choose_tilted_grasp.py`, `probe_articulation_refine.py`); no config, no ported module and no
`skills/` file was modified, so the 5/5 top-drawer capability is untouched.

## The environment's own success criterion (read, not guessed)

`Open.__call__(arg)` is just `arg.is_open()`
(`liberopro/envs/predicates/base_predicates.py:101`), and `WoodenCabinet` defines
(`liberopro/envs/objects/articulated_objects.py:173-188`):

```python
self.object_properties["articulation"]["default_open_ranges"] = [-0.16, -0.14]
self.object_properties["articulation"]["default_close_ranges"] = [0.0, 0.005]

def is_open(self, qpos):
    return qpos < max(self.object_properties["articulation"]["default_open_ranges"])   # qpos < -0.14
```

So the task is satisfied as soon as the drawer joint passes **-0.14**, i.e. **14.0 cm of travel**.
That is looser than what our own binding asks for:

| target | required travel | source |
| --- | --- | --- |
| environment `check_success()` | **14.0 cm** (`qpos < -0.14`) | `default_open_ranges` above |
| our binding `open_range [-0.155,-0.145]` (skill aims at the mean -0.15) | 15.0 cm | `libero90_drawer_articulation_config` |

Cross-check from the working top-drawer runs: they terminated at joint **-0.14018** with
`completion=environment_task_success` and `cleanup_complete=False` - i.e. the executor stops on the
environment's criterion, just past -0.14, and never needs the planner's full 15 cm.

Consequence for the bottom drawer: the requirement is 14.0 cm (not 15.0), and the best tilted grasp
reaches **11.5 cm**. So the answer to "would 0.115 m count as success?" is **no** - it is 0.025 m
short - and re-targeting the binding to the environment's threshold would only buy back 1.0 cm.
Worth doing anyway (the skill should not over-ask by 1 cm), but it does not unlock the task.

## Grasp-point sweep and mid-travel re-grasp: both fail, and the blocker is not the arm

`probe_travel_grid.py` sweeps (tilt, offset along the horizontal handle bar) and walks the slide the
way `refine_articulation` does. Note the bar is **horizontal**: its long axis is world +x (the
brackets g41/g42 sit at +-0.032 in x at the same z), so "grasp higher on the bar" does not exist -
sideways along the bar does.

A first version of this walk only asked whether each step's IK returned a solution; it reported
15 cm of travel for tilt 40/50. That was **wrong** - it omitted `refine_articulation`'s joint-jump
and `valid()` checks, and the full solve rejected exactly those candidates. With the checks mirrored:

| tilt / dx | steps (of 30) | travel | failure |
| --- | --- | --- | --- |
| 35 / +0.02 | 14 | 0.070 m | `drawer_overlaps_fixed` |
| 40 / +0.02, 40 / 0 | 14 | 0.070 m | `drawer_overlaps_fixed` / `ik_failed` |
| 45 / 0 | 14 | 0.070 m | `drawer_overlaps_fixed` |
| 45 / -0.02 | 14 | 0.070 m | `articulation_ik_jump` |
| 50 / +0.02, 50 / 0, 50 / -0.02 | 14 | 0.070 m | `drawer_overlaps_fixed` |
| 55 / all three | 14 | 0.070 m | `drawer_overlaps_fixed` |
| 35 / 0, 35 / -0.02, 40 / -0.02 | 7-13 | 0.035-0.065 m | `ik_failed` |

**Every candidate stops at <= 7 cm; none reaches the environment's 14 cm.** Changing the grasp point
does not unlock the task.

Mid-travel re-grasp (`--mode regrasp`, pull to -0.07 then grasp again in the moved scene):

| re-grasp candidate | re-grasp reachable | one further step? |
| --- | --- | --- |
| same tilt | yes (IK + free motion, 32 pts) | **no** - `drawer_overlaps_fixed` |
| tilt 60 | yes | **no** - `drawer_overlaps_fixed` |
| horizontal | no (IK fails) | - |
| tilt 30, other side | free motion ok, grasp IK fails | - |

### What actually blocks the pull (named)

`valid_detail` reports the failing rule; it is the moving-vs-fixed box overlap, and the fixed geom is
**not part of the cabinet**:

```
drawer_overlaps_fixed(geom_195 | geom_160)
geom 195 = wooden_cabinet_1_g33   owner=wooden_cabinet_1_cabinet_bottom  (moving with the joint)
geom 160 = plate_1_g9             owner=plate_1_main                     (the plate on the table)
```

`audit_overlap_pair.py` on the recorded problem: the drawer's panel at s = -0.070 has
y in [-0.0913, -0.0859] while the plate's box has y in [-0.0817, -0.0429] - a 4.2 mm gap; one more
5 mm step puts them into a sliver overlap. So the drawer is stopped by **the plate lying on the table
in front of the cabinet**, with about a millimetre of proxy interference, not by the robot.

This is separate from the original failure (the horizontal grasp's approach pose has no IK, which the
tilted grasp does fix: the approach then passes). Both problems exist for this drawer.

Caveat: the overlap verdict is criss-cross oriented-box SAT on **coarse box proxies** (the plate's rim
is a box, and the drawer part g33 is a 6.8 cm x 21.9 cm vertical plate). The real MuJoCo geometry may
clear by a few millimetres. Confirming it needs either a mesh-accurate check of those two proxies or
watching real contacts while the drawer is driven open.

### The pull has three separate blockers, and they are now decomposed

Using the code's own `allowed_pairs` mechanism to take scene objects out of the *drawer's* way (they
still block the robot), the strict walk gives:

| what is allowed through | tilt | steps (of 30) | travel | reaches 14 cm | stops because |
| --- | --- | --- | --- | --- | --- |
| nothing | 40/45/50/55 | 14 | 0.070 m | no | `drawer_overlaps_fixed(geom_195 &#124; plate_1_g9)` |
| all `plate_1` geoms | 40 | 20 | 0.100 m | no | arm IK fails |
| all `plate_1` geoms | 45 | 20 | 0.100 m | no | `...&#124; geom_106` = `akita_black_bowl_1_g22` |
| `plate_1` + `akita_black_bowl_1` | 40 | 20 | 0.100 m | no | arm IK fails |
| `plate_1` + `akita_black_bowl_1` | 45 | 22 | 0.110 m | no | arm IK fails |
| **`plate_1` + `akita_black_bowl_1`** | **50** | **30** | **0.150 m** | **yes** | - |
| **`plate_1` + `akita_black_bowl_1`** | **55** | **30** | **0.150 m** | **yes** | - |

So the bottom drawer has three independent blockers, in order:

1. **Approach** - the configured horizontal grasp pose has no IK (proven collision-free: the empty
   world still fails). A tilted grasp fixes this.
2. **Scene objects in the drawer's path** - the drawer's own moving geometry overlaps the **plate**
   (`plate_1`, g9/g10) at ~7 cm and the **black bowl** (`akita_black_bowl_1_g22`) at ~10.5 cm. Both
   sit on the table directly in front of the cabinet, and the drawer slides towards the robot.
3. **The arm's own IK** - with a clear path, tilt 40/45 still die at 10-11 cm; tilt 50/55 complete
   the full 15 cm.

Answering "did the tilted grasp fail because of the plate?": **no**. The tilt is what makes the
approach work at all; the plate stops the *pull*, and it would stop any grasp, because it is the
drawer's own geometry that hits it. The plate is blocker 2 of 3, not the cause of the tilted grasp's
failure as such.

Practical consequence: the BDDL goal only requires `open(wooden_cabinet_1_bottom_region)`; nothing
constrains where the plate or the bowl are. So a legitimate plan is **clear the plate (and bowl) out
of the drawer's path, then open the drawer with a 50-55 deg grasp**. The current recipe forces
articulation as the only recovery goal at query 0, so it could never do that.

Caveat before investing in that: the moving proxies are coarse - the bottom drawer's `g33` is a
6.8 cm x 21.9 cm vertical plate, which sweeps a far larger volume than a real drawer side. A
mesh-accurate check (or watching real contacts while the joint is driven) should confirm that the
plate/bowl obstruction is real and not a proxy artifact.

## Run with the drawer-vs-scene overlap ignored (tilt 50 deg)

An opt-in key was added to the articulation config: `ignore_drawer_environment_overlap: true`
(read in `CuroboArticulationMotion.__init__`, default **off**). It skips only this extension's own
moving-vs-fixed box bookkeeping; the robot's own collision checks stay on, and LIBERO's simulator owns
the drawer-vs-object contacts. The config reaches the backend because
`real_cutamp_adapter.py:1426` copies the whole config dict into `hints["articulation"]`.

Pre-flight then accepted a candidate for the first time and wrote a **new** temp config
(`articulation_drawer_bottom_tilt.json`, tilt 50 / dx 0, tool centre (0.6844, -0.0702, 0.1081));
nothing existing was edited. Three runs, 5 episodes each, `--save_video`:

| run | suite / task | config | result |
| --- | --- | --- | --- |
| goal_t01_tilt | libero_goal_task 1 (bottom) | tilt 50 + ignore overlap | **0/5** |
| t07_bottom_tilt | libero_90 7 (bottom) | tilt 50 + ignore overlap | **0/5** |
| t08_top_regression | libero_90 8 (top) | the untouched top config | **5/5** (regression intact) |

Failure mode moved forward, but not to success:

- t1: ep00-03 planned fine and **executed 58 approach rows** (`approach:56/57` succeeded,
  `:58` failed) then `optimized_motion_tracking_stalled`; ep04 failed planning
  (`articulation_ik_failed`). `articulate=0` everywhere, so the grasp was never reached.
- t7: ep00 stalled the same way at `approach:57`; ep01/03/04 failed planning with
  `articulation_ik_jump`, ep02 with `articulation_ik_failed`.
- t8: 5/5 with the baseline signature (approach 72-76, articulate 60, joint -0.1402, queries 1,
  frames 403/403/403/421/401 - identical to the archived success).

Videos (kept, plus 12-frame contact sheets): `E:\VLA_recovery_workspace\tilt_grasp_20260927\`.
They show the tilted approach actually reaching the bottom drawer front and then withdrawing with the
drawer still closed, with the plate sitting right in front of the drawer.

So the remaining blocker is downstream of planning: the executor cannot track the final approach
waypoint (the grasp pose) - consistent with this pose sitting at the edge of the arm's reachable set,
which is exactly why the planner needed a 50 deg tilt to accept it at all.

### Rollback (verified)

```
articulation_drawer_bottom_tilt.json          deleted (no longer exists)
articulation_drawer_top.json                  832376aebcee0b17abc190865274870a  (unchanged)
articulation_drawer_bottom.json               5da3c3bdd3a117d1dcc6971375a6fae0  (unchanged)
libero90_drawer_articulation_language.json    78632a6a567c647c0ed15f26a34219c2  (unchanged)
t08 regression                                5/5 with the modified articulation_curobo.py in place
```

The only code change kept is the opt-in `ignore_drawer_environment_overlap` flag (default off); the
sealed pack, the top/bottom configs and the skill index were never modified.

## Next steps (not yet run)

1. Probe cuRobo IK for the bottom handle pre-grasp directly (sweep the grasp z-offset, yaw, and
   approach direction) to find a reachable pre-grasp, in the spirit of
   `scripts/recovery/skill_pipeline/probe_grasp_validity_sweep.py`; then re-run task1 and task7.
2. If no top-down pre-grasp is reachable, try a front-facing (horizontal) approach for the bottom
   handle, or accept a pre-grasp generated from the current state.
3. Keep `--save_video` for every run and pull to a local folder; judge from the video.

## Artifacts

- Local (openable): `E:\VLA_recovery_workspace\goal_task1_bottom_20260927\` (5 videos, `*_sheet.png`
  contact sheets, `episode.json`, `recovery_trace.jsonl`, `summary.json`, `eval.log`, `runner.log`,
  `cutamp_debug/solve_*.problem.json`)
- Local: `E:\VLA_recovery_workspace\task7_bottom_20260927\` (5 videos, sheets, traces, `summary.json`)
- Server: `$SSD/articulation_drawer_bottom.json` (filtered single binding),
  `$SSD/libero90_drawer_articulation_language.json` (source multi-entry config)
- Scripts: `.inspire/run_goal_task1_bottom_5ep.sh`, `launch_goal_task1_bottom_5ep.sh`,
  `poll_goal_task1_bottom.sh`, `pull_goal_task1_bottom_videos.sh`, `run_task7_bottom_5ep.sh`,
  `launch_task7_bottom_5ep.sh`, `pull_task7_traces.sh`, `pull_task7_bottom_videos.sh`,
  `montage_videos.py`, `inspect_problem.py`
