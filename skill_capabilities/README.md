# Skill Capability Registries

Skill indices may declare a `capability_registry` path.  The registry lists the
runner, grounding, geometry, grasp, and executor capabilities that skills in
that index are allowed to use.

This is a CI-style guardrail for skill mining: Codex can still draft skills, but
admission and online validation reject a draft if its `recovery_hints` call an
unregistered code path.

- `libero90_legacy.yaml` covers the current LIBERO-90 online skill library.
- `core_minimal.yaml` is the clean starting point for a new isolated skill
  library.
- `generated_scratch_v1.yaml` documents the one legacy grasp profile currently
  used by the generated-task scratch draft.
