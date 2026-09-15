# Skill Capability Registry

The capability registry is a guardrail between a declarative skill library and
the low-level code paths that implement grasp, repair entry, grounding,
geometry, place, and executor behavior.

## Purpose

During mining, Codex may draft a skill that mentions an existing
`grasp_profile`, `repair_profile`, `grounding_profile`, `geometry_profile`,
`place_profile`, raw hint key, planner primitive, geometry descriptor shape, or
executor option. Those names are not just markdown text: runtime expands them
into code paths in the matcher, runner, cuTAMP adapter, scene builder, or
executor. A registry makes this dependency explicit.

## Runtime Placement

1. The active skill pack declares `capability_registry` in `pack.yaml` or
   `skills/_index.yaml`.
2. The online runner resolves `--skill_pack`, then loads that registry together
   with the pack skill index and profile registries.
3. When a repair trigger fires, runtime merges matching recovery hints.
4. Runtime expands named grounding / geometry / repair / place profiles, audits
   the merged hints against the registry, then attaches the pack-local grasp
   adapter path.
5. If any hint uses an unregistered capability, runner raises a schema error
   instead of silently reusing old behavior.

Engine-consumed names are defined once in
`experiments/robot/libero/tiptop_repro/engine_capabilities.py`. The pack
registry is a stricter allowlist layered on top of that engine list:

- engine support means the low-level code knows how to consume the name;
- pack registration means this skill pack is allowed to use it.

A new skill must satisfy both. Adding a name to `capabilities.yaml` alone does
not create executor behavior, geometry construction, or planner support.

Admission uses the same registry before ingesting a draft.  This keeps the
offline gate and the real validation run aligned.

## Registries

- `skill_packs/libero90_legacy/capabilities.yaml`: current online LIBERO-90
  skill library. It intentionally allows the legacy helper code validated on
  LIBERO-90.
- `skill_packs/generated_v1/capabilities.yaml`: scratch generated-task mining
  library. It should stay narrow and only add capabilities that the generated
  pack actually owns.

Older `skill_capabilities/*.yaml` files may exist for compatibility, but the
pack-local files above are the source of truth for current mining.

## CLI Usage

Most commands can infer the registry from `_index.yaml`.  To override it:

```bash
python scripts/recovery/skill_pipeline/run_skill_eval.py \
  --enable_mining_skills \
  --skill_pack generated_v1 \
  ...
```

Admission:

```bash
python scripts/recovery/skill_pipeline/run_skill_admission.py \
  --skill-file path/to/draft.md \
  --skill-pack generated_v1 \
  --out-dir path/to/gate
```

## How To Use For New Mining

Start new task mining from a scratch skill pack with a narrow registry. If a
draft genuinely needs a new code path, add that capability deliberately, with a
test, `code_patch_manifest.yaml`, and an explanation. Otherwise the draft should
stay within the declared surface.

Current capability categories:

| category | Meaning |
| --- | --- |
| `grasp_profiles` | Object-specific grasp sampler names selected by `recovery_hints.grasp_profile`. |
| `repair_profiles` | Recovery-entry executor parameter bundles. |
| `grounding_profiles` | Named semantic binding profiles expanded from `profiles/grounding.yaml`. |
| `geometry_profiles` | Named planner geometry profiles expanded from `profiles/geometry.yaml`. |
| `place_profiles` | Named place policy profiles expanded from `profiles/place.yaml`. |
| `grounding_hint_keys` / `grounding_hint_intents` | Raw grounding hint slots and pack-level intent names. |
| `geometry_hint_keys` / `geometry_hint_intents` | Raw geometry hint slots and pack-level intent names. |
| `executor_options` | Low-level executor config keys accepted by `LiberoRobotClientConfig`. |
| `place_candidate_policies` | Planner place candidate selection policies. |
| `place_yaw_policies` | Planner / executor yaw policies. |
| `release_modes` | Executor release behavior modes. |
| `geometry_descriptor_shapes` | Generic geometry descriptor shapes such as `box`, `rotated_box`, `cylinder`, `sphere`. |

For profile-backed skills, the preferred pattern is:

```text
skill markdown -> params.<type>_profile -> profiles/<type>.yaml
               -> code/<type>_profiles.py or code/place_policies.py
               -> generic engine primitive / supported executor option
```

Raw inline hints are acceptable only while drafting a new profile. Final online
skills should reference registered profiles so the dependency is visible in the
pack registry and inspectable by admission.

Code admission checks only two hard properties:

- changed files remain inside the extension boundary for the declared
  `change_type`;
- any capability used or added by the patch is registered in the active pack.

It is not a substitute for code review or rollout validation; it is a guardrail
that prevents task-specific skill code from leaking into unrelated paths.
