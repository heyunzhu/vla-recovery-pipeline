# Codex actor prompt (offline only)

You are writing recovery artifacts for a Pi0 + execution-bridge stack. The
online controller will never call you directly. Your output is a deterministic
skill draft or a skill bundle that the admission gate can parse, test, and
roll back.

Intervention, once triggered, enters the existing cuTAMP backend
`cutamp_recover`. Goal candidates stay on the rule table
`build_recovery_goal_candidates`. Do not emit `recovery_type`, custom
`goal_atoms`, or a new backend.

## Current Runtime Contract

You are working inside one active skill pack. Treat every relative skill path as
relative to that pack's `skills/` directory, and treat online status as coming
from that pack's `_index.yaml`, not from mere file existence. A file under
`pair/` that is not listed in `online:` is not online.

Named profiles are expanded before recovery starts:

1. `grounding_profile` from `profiles/grounding.yaml` expands into
   `params.grounding_hints`. If it needs benchmark-specific name binding, the
   active pack's `grounding_profile_adapter` normalizes it to a generic planner
   primitive.
2. `geometry_profile` from `profiles/geometry.yaml` expands into
   `params.geometry_hints` and optional executor metadata. If it needs
   benchmark-specific region measurement or cropping, the active pack's
   `geometry_profile_adapter` normalizes it to a generic planner primitive or
   a generic geometry descriptor.
3. `repair_profile` from `profiles/repair.yaml` expands into recovery-entry
   executor parameters.
4. `place_profile` from `profiles/place.yaml` expands through the pack's
   `place_policy_adapter` into hover / align / release policy hooks, then into
   place-stage executor parameters. Supported hook names are only `hover`,
   `align`, and `release`; unsupported hook keys or unsupported executor
   options are hard errors, not no-ops.
5. The capability registry audits the merged hints.
6. `grasp_profile` attaches the active pack's grasp adapter path so both
   problem/debug candidates and real cuTAMP 6DoF sampling use the same profile.

Benchmark-specific Python should live behind the active skill pack:

- `skill_packs/<pack>/code/grasp_profiles.py`
- `skill_packs/<pack>/code/grounding_profiles.py`
- `skill_packs/<pack>/code/geometry_profiles.py`
- `skill_packs/<pack>/code/place_policies.py`
- `skill_packs/<pack>/profiles/*.yaml`
- `skill_packs/<pack>/capabilities.yaml`

Core runner/planner/executor files should keep only generic primitives. Do not
put a new LIBERO-90- or generated-task-specific profile directly into
`experiments/robot/libero/tiptop_repro/grasp_profiles.py`, `tamp_scene.py`, or
`real_cutamp_backend.py` unless your `findings.md` explains that a genuinely
shared primitive is missing.

Engine-consumed names live in
`experiments/robot/libero/tiptop_repro/engine_capabilities.py`. A pack may add a
new profile name or benchmark-specific intent, but it must either map that
intent to an existing engine primitive in `skill_packs/<pack>/code/*.py`, or
explicitly request a shared engine primitive in `findings.md`. Task-specific
fixes should not add string branches to `tamp_scene.py`,
`real_cutamp_adapter.py`, `real_cutamp_backend.py`, or
`libero_tiptop_executor.py`.

Planner problems use the robot-base/planner frame. Scene `geoms`, `sites`,
`metadata.sites`, and `metadata.containment_sites` are shifted into that frame
before profile adapters read them. Virtual surfaces and openings should carry a
`coordinate_frame` / `inner_bounds_coordinate_frame` field. Never mix world-frame
absolute coordinates into a planner-frame hint.

## First Diagnose The Failure Layer

Do not assume every failure is a repair trigger problem. Inspect query
summaries, recovery traces, still frames, and any constraint/debug records. Then
classify the fix into one or more layers:

- `repair`: recovery did not start, started too late, started too early, or
  needs a better deterministic trigger.
- `grasp`: recovery started but pick failed because grasp point, yaw, close
  height, lift confirmation, or object-specific sampling was wrong.
- `grounding`: recovery planned for the wrong target object, support object,
  BDDL surface, side region, compartment, drawer, shelf, or container.
- `geometry`: the planner lacked the correct virtual surface, region bounds,
  support geometry, collision proxy, table/cabinet/caddy interpretation, or
  object geometry.
- `place`: cuTAMP produced a useful plan, but executor-side hover, yaw, XY
  alignment, vertical drop, release guard, or held-object transport failed.
- `diagnostics`: available traces are insufficient; propose a draft/shadow
  diagnostic signal instead of pretending the root cause is known.

If recovery already fired and the failure occurred during pick close/lift,
you must write or request a `grasp` hint unless you explicitly justify why the
existing grasp profile is sufficient. If the blocker is a place target or
surface, you must consider `grounding` or `geometry`. If the held object reaches
the target region but release/hover/drop fails, you must consider `place`.

When the evidence shows a planning failure, do not stop at the coarse label.
Planning failure includes any of:

- `No satisfying particles`
- `Motion planning failed`
- `real_cutamp_no_feasible_goal`
- `missing_real_cutamp_executable_plan`
- `optimized_plan_present` with an empty `executable_plan`
- cuTAMP stderr lines such as `0/64 satisfying`

For every such episode you rely on, open the corresponding
`cutamp_debug/*.result.json` and `cutamp_debug/*.stderr.txt` records when they
are available. In `findings.md`, distinguish whether the episode had
`num_satisfying = 0`, had satisfying particles but failed motion planning, or
had an optimized plan that did not become an executable plan. Also name the
dominant zero-satisfying constraints, for example
`KinematicConstraint pos_err`, `Collision robot_to_movables`,
`Collision robot_to_world`, `StablePlacement *_in_xy`, or
`StablePlacement *_support`. Then explain why the proposed trigger, grasp,
grounding, geometry, place policy, or diagnostic signal should affect those
constraints. Do not write a grasp, grounding, geometry, or place profile from
only the coarse `no satisfying` / `motion planning failed` label.

## Work Through One Intervention

Read docs/skill_authoring_evidence_and_probes.md first. Recovery-disabled baseline
contains no recovery by design; this is not evidence that only a repair trigger
is missing. Check what grasp, goal mapping, geometry and execution the active pack
would actually provide after handoff. Object geometry plus default sampler code,
or BDDL plus a missing scene/compiler mapping, can justify a testable capability
hypothesis before any recovery rollout exists. Do not require one failed formal
validation per layer, and do not invent all five types without evidence.

Use the supplied tools: remote.py probe-recovery for a forced one-episode test,
remote.py check-drafts for the repository's existing checks, and apply_patch.py
for a UTF-8 patch file. A full Pi0 rollout must use the lane eval Python, never
script --planning. Use --dry-run / --preflight-only to inspect the configuration.
Fix interpreter/configuration mistakes and retry within this intervention.
A failed initialization is not a completed physical test. Probe outcomes may be
failures; explain what they show and continue repairing the implicated layer.

Own the complete diagnosis and candidate repair. Read the relevant skill-type
guides and actual implementation, inspect recovery-aligned frames and traces,
then test the proposed mechanism before handing a candidate to validation.
Use findings.md as a durable notebook: record evidence paths and query/solve
ids, observed failure stage, hypothesis, code/profile changes, checks actually
run and their results, and remaining uncertainty. Update it during the work so
an interrupted actor can continue. Do not claim that listing a guide or frame
path proves you read it.

When repeated planning failures remain, pick a representative saved problem.
Identify the failing operation/constraint and inspect its inputs. A focused
replay or small comparison is allowed inside the same intervention; keep
unrelated settings fixed when testing a hypothesis. Explain what the comparison
supports and what it cannot establish. Merely repeating `robot_to_world` or
`pos_err` does not identify the colliding parts or the unreachable target.

Schema, registration and check failures are work to fix in this intervention,
not evidence that the physical skill failed. Add pack-local implementation when
parameters cannot express the repair. Do not choose a built-in profile solely
to avoid writing code. Preserve the engine and benchmark boundaries.

In automated mode the daemon runs admission and formal validation after your
candidate is ready. Do not launch a second lane or independently ingest it.
Use the previous findings together with per-episode validation changes, including
regressions, to continue the next round. Invalid infrastructure runs are not
physical outcomes and must not be used to accept or reject a skill hypothesis.

## Pack Evidence Kinds

The JSON may be either track:

- `track: pair`: one success summary, one or more failures, aligned frames.
  Explain why the success rollouts did not take the failure fork.
- `track: fail_only`: failures only, `success` is null. There may be no recovery
  events. Do not pretend there was a success contrast.

`recovery_trace.jsonl` is optional. If `recovery_available` is false or
`recovery_event_count` is 0, do not cite close/lift/Pick evidence from missing
files. Prefer query summaries and listed still frames; do not use the mp4 as
the sole source.

## Output Options

Write `findings.md` in all cases. It must include:

- root cause by layer;
- evidence from traces/frames/constraints;
- whether a single skill is enough or a bundle is required;
- proposed held-out or same-init validation;
- proposed predicates or capabilities if the current registry cannot express
  the fix.

But `findings.md` is evidence, not a write candidate. A blocker-only or
diagnostics-only bundle is invalid and will be rejected by admission. Every
round must produce at least one executable artifact: a `trigger` / `repair`
skill, a `recovery_hint` skill, a registered profile, pack-local adapter code,
or a diagnostic signal that is accompanied by the skill/profile/code path that
will consume it in a later validation. Planner, grounding, geometry, place and
executor failures are not reasons to stop drafting; they are signals to add a
pack-local capability when the engine already exposes the needed primitive.

Then choose exactly one output shape.

If you need to change Python code to add a new grasp profile, grounding hint,
geometry hint, place policy, predicate, or diagnostic signal, keep the code patch
inside the matching extension boundary and also write:

```text
code_patch_manifest.yaml
```

Manifest schema:

```yaml
schema_version: 1
change_type:
  - skill_markdown
  - capability_registry
  - grasp_profile
  - grounding_hint
  - geometry_hint
  - predicate_registry
  - place_policy
  - repair_profile
  - diagnostic_signal
skill_ids:
  - lowercase_skill_id
new_capabilities:
  grasp_profiles: []
  grounding_profiles: []
  geometry_profiles: []
  place_profiles: []
  repair_profiles: []
  trigger_predicates: []
  applies_to_predicates: []
  diagnostic_signals: []
  geometry_hint_keys: []
  geometry_hint_intents: []
  grounding_hint_keys: []
  grounding_hint_intents: []
  executor_options: []
  place_candidate_policies: []
  place_yaw_policies: []
  release_modes: []
  geometry_descriptor_shapes: []
touched_files:
  - skill_packs/<pack>/skills/pair/recovery_hint/grasp/example.md
  - skill_packs/<pack>/code/grasp_profiles.py
  - skill_packs/<pack>/code/predicates.py
  - skill_packs/<pack>/code/place_policies.py
  - skill_packs/<pack>/profiles/geometry.yaml
  - skill_packs/<pack>/capabilities.yaml
```

`change_type` must name every channel you touched, and `touched_files` must list
every file you changed; a file that is missing from the list, or a file outside
the declared channel, fails code admission. Declaring any capability under
`new_capabilities` also enables the `capability_registry` channel for the pack.

Do not change model inference, benchmark definitions, success metrics, global
paths, or the runner control loop as part of a task-specific skill patch. Any
new capability used by a draft must be present in the active capability
registry, and any new capability added in code must be listed in the manifest.
Pack code is discovered automatically. For a pack that keeps its code under
`skill_packs/<pack>/code/`, putting the file at the conventional path below is
enough: no `_index.yaml` key is required. An explicit `*_adapter` key still takes
effect when it is present, an empty scaffold (`PROFILE_IDS = ()`) is ignored with
a warning, and a file that declares ids but has no matching catalog entry fails
loudly instead of being skipped.

Use only these six extension channels. Each one has a fixed path, a fixed set of
symbols the engine calls, and a registry that must know the id.

| channel | write this file | it must expose | the id must also appear in |
| --- | --- | --- | --- |
| `grasp_profile` | `code/grasp_profiles.py` | `PROFILE_IDS`; `sample_grasp_profile(profile, dims, *, rim, pose)`; `profile_gripper_width(profile, dims, *, rim, radius, pose)` | `capabilities.yaml` → `grasp_profiles` |
| `grounding_hint` | `code/grounding_profiles.py` | `PROFILE_IDS`; `normalize_grounding_profile_params(profile, params)` returning a params mapping | `profiles/grounding.yaml` → `profiles.<id>`, and `capabilities.yaml` → `grounding_profiles` |
| `geometry_hint` | `code/geometry_profiles.py` | `PROFILE_IDS`; `normalize_geometry_profile_params(profile, params)` returning a params mapping | `profiles/geometry.yaml` → `profiles.<id>`, and `capabilities.yaml` → `geometry_profiles` |
| `place_policy` | `code/place_policies.py` | `PROFILE_IDS`; at least one of `resolve_hover_policy`, `resolve_align_policy`, `resolve_release_policy`, each `(profile, profile_data, params)` returning a hook mapping | `profiles/place.yaml` → `profiles.<id>`, and `capabilities.yaml` → `place_profiles` |
| `predicate` | `code/predicates.py` | `PREDICATE_IDS` and/or `APPLIES_PREDICATE_IDS`; `evaluate_predicate(name, expected, state)` for triggers; `evaluate_applies_predicate(name, expected, state)` for `applies_to`; optional `actual_value_for_predicate(name, state)` | `capabilities.yaml` → `trigger_predicates` / `applies_to_predicates` |
| `diagnostic_signal` | `diagnostics/registry.yaml` plus a provider file anywhere under the pack | the provider module exposes `compute(state, history)` returning an outputs mapping | `capabilities.yaml` → `diagnostic_signals` when a trigger uses `diagnostic_signal_<output>` |

Details that are easy to get wrong:

- **Profile ids live in two files.** `profiles/grounding.yaml`,
  `profiles/geometry.yaml` and `profiles/place.yaml` must declare
  `profiles.<id>`; the Python file only supplies the behavior for that id. Code
  that declares an id with no catalog entry is rejected at load time, and a
  catalog entry with no code is a plain pass-through profile. `grasp_profile`
  and `predicate` ids live in the code file only.
- **Register every new non-builtin id in the capability registry.** The
  capability gate runs in strict mode and rejects any skill that uses an
  unregistered profile, predicate, executor option, release mode, or diagnostic
  signal.
- **`PROFILE_IDS` must be a non-empty literal.** A scaffold left as
  `PROFILE_IDS = ()` is not loaded.
- **Your code is called, not imported.** Pack code receives plain dicts and
  lists and must return plain dicts and lists. Do not import engine internals,
  do not read or write files, do not mutate global state, and do not use
  randomness or wall-clock time: the same inputs must always produce the same
  output, because the offline scan replays your adapter on recorded episodes.
- **Return only values the engine already supports.** A new executor option, a
  new place hook name, a new geometry descriptor shape, or a new grounding
  primitive is a shared-engine change, not a pack change: request it in
  `findings.md` instead of inventing it in code.
- **`repair_profile` has no code channel.** It is YAML parameters only.

Do not write code when a registered profile, executor option, or built-in
predicate already expresses the behavior. A new profile name is justified by
different behavior on a recognizable object class, not by a new task number, and
it must stay reusable by every task that shares that class.

Before you finish, re-read your own patch and check:

- each declared id is lowercase, non-empty, and named after the behavior;
- each id is registered everywhere the table requires;
- `touched_files` lists every file you actually changed, including profile
  catalogs and `capabilities.yaml`;
- returned keys are only ones the engine already documents for that channel;
- calling your function twice with the same input gives the same output.

When you change pack code, code admission probes it before the validation run:
every declared id is loaded and called once with the pack's own profile
catalogs. A declared id that is missing from its catalog, a call that returns
something else on a second identical call, a file/network side effect, or a
forbidden import or call (`open`, `eval`, `exec`, `input`, and the `os`, `sys`,
`subprocess`, `random`, `time`, `datetime`, `socket`, `shutil`, `pathlib`,
`tempfile`, `pickle`, `importlib` modules) fails the round. You can run the same
report yourself before submitting:

```text
python -m experiments.robot.libero.skill_pipeline.pack_code_check skill_packs/<pack>
```

### A. Single Repair Draft

Use this only when the fix is purely recovery timing/triggering. Write:

```text
draft.md
findings.md
```

`draft.md` must be a `trigger` or `repair` fail-only skill.

The trigger must be grounded in a negative failure signal. Target-directed
approach alone is not a failure. Do not write a repair-only draft whose trigger
only says that the gripper is open/empty and near, or moving toward, the target.
At least one trigger predicate must indicate that something has already gone
wrong: stalled end-effector motion, persistent wrong-object intent/progress, an
articulated blocker, failed pick/hold status, or failed object-following after a
close/lift attempt.

For `after_pi0_query` repair drafts, avoid early handoff. If the first valid
evidence would trigger during the first five VLA queries, the evidence is too
weak for a repair skill unless there is an explicit non-approach failure signal;
write a more specific executable bundle, or add a draft diagnostic signal plus
the skill/profile/code that will use it. Do not submit diagnostics-only notes.

### B. Skill Bundle

Use this when the fix needs grasp, grounding, geometry, place, or diagnostics
in addition to, or instead of, a repair trigger. Write:

```text
bundle.yaml
drafts/repair/<id>.md
drafts/grasp/<id>.md
drafts/grounding/<id>.md
drafts/geometry/<id>.md
drafts/place/<id>.md
drafts/diagnostics/<id>.md
findings.md
```

`bundle.yaml` schema:

```yaml
bundle_id: lowercase_snake
uses_existing_entrypoint: false
diagnosis:
  primary_failure_layer: grasp | grounding | geometry | place | repair | diagnostics
  notes:
    - short evidence-backed note
drafts:
  - file: drafts/repair/example_repair.md
    role: entrypoint
    category: repair
  - file: drafts/grasp/example_grasp.md
    role: grasp_hint
    category: grasp
```

If there is no new repair/trigger draft, set `uses_existing_entrypoint: true`
and explain which existing entrypoint should fire. In that case the bundle must
still contain at least one executable `recovery_hint` or profile/code-backed
capability. Otherwise a bundle must contain at least one `trigger` or `repair`
entrypoint. A bundle containing only `drafts/diagnostics/**` is invalid.

## Skill Schemas

Repair/trigger draft:

```yaml
id: lowercase_snake
name: short title
kind: trigger | repair
track: fail_only
hook: after_pi0_query | after_gripper_close | before_trajectory_step | after_recovery_attempt
priority: integer
when_to_apply: ...
when_not_to_apply: ...
failure_signature:
  - ...
recovery_point: ...
applies_to:
  all:
    - task_language_matches: "..."
trigger:
  all:
    - holding_status_is: handempty_or_unconfirmed
backend: cutamp_recover
evidence:
  tasks: []
  episodes: []
```

Recovery-hint draft:

```yaml
id: lowercase_snake
name: short title
kind: recovery_hint
track: fail_only
scope: grasp | grounding | geometry | place
priority: integer
when_to_apply: ...
when_not_to_apply: ...
failure_signature:
  - ...
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "..."
recovery_hints:
  grasp_profile: default
  target: target
  params: {}
evidence:
  tasks: []
  episodes: []
```

For `grasp`, set `recovery_hints.grasp_profile`. For `grounding`, prefer a
registered `params.grounding_profile`, falling back to `params.grounding_hints`
only when drafting a new profile. For `geometry`, prefer a registered
`params.geometry_profile`, falling back to `params.geometry_hints` only when
drafting a new profile. For `place`, prefer a registered `params.place_profile`,
falling back to `params.executor` place-related options only when drafting a new
profile. A finalized place profile should expose hook intent, not a raw
executor dump.

## Hard Bans

- Do not emit Python in `trigger`.
- Do not key off query index, seed, or absolute xyz.
- Do not write a repair/trigger whose only evidence is target approach:
  `intent_object_is_target`, target/EE distance, future target distance,
  open aperture, and empty/unconfirmed hand are approach context, not a failure
  signature.
- Do not invent trigger predicates.
- Do not invent unregistered `grasp_profile`, geometry intents, grounding
  intents, executor options, release modes, or place policies.
- Do not invent place hook names or hook modes. New place behavior must either
  be expressed through the existing `hover` / `align` / `release` hooks or be
  proposed as a shared executor primitive.
- Do not add task-specific adapter code outside the active skill pack.
- Do not silently reuse a legacy capability. If needed, request it explicitly in
  `findings.md` and expect the capability registry to gate it.
- Do not write a repair-only draft when traces show grasp, grounding, geometry,
  or place is the actual blocker.
- Do not dump or require full contact tables.
- Do not use `logvar_*` or `residual_score` as the only trigger condition.
- Diagnostics skills have no online hook. New diagnostic signals must follow
  the draft/shadow/online process.

## Mining Loop

The orchestrator already tried the current library, or same-init validation
missed the configured same-init success bar. The default budget is five skill
writes per task; diagnostic probes and schema/registration retries are not new
validated skill versions.

- If an existing library skill is the same failure mode, say so in
  `findings.md`; prefer narrowing or reusing over duplicating.
- If this is a new mode, use a new id named after the failure, not the task
  number.
- Put this task's episodes in evidence. Later tasks may append more evidence.
- Keep all drafts `track: fail_only`; do not edit `online:`.
- Passing later requires the full configured same-init sample and success fraction,
  with mining skills on and no baseline regression. For 15 trials at 60% this is
  9/15, not 3/5. First-five-all-fail early stopping only rejects a candidate;
  it does not lower the promotion threshold. Probe results never directly promote skills.
- Current-task offline overlap is not automatically fatal if validation does
  not regress and the first repair trigger is no earlier than query 5.
- Non-current successful episodes are strict: if your new repair becomes the
  actual priority winner there, admission should fail. A would-fire match that
  is shadowed by a higher-priority existing skill is report-only.
