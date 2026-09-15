# Generated LIBERO Skill Benchmark

This directory was generated from source LIBERO BDDL tasks. It is intended for
skill-mining and harness validation, not as a replacement for the original
LIBERO benchmark.

## Summary

- source tasks: 90
- generated tasks: 304

## Splits

- `smoke`: 3
- `train`: 256
- `validation`: 45

## Templates

- `caddy_compartment`: 124
- `pick_place_on_surface`: 67
- `put_inside_container`: 113

## Files

- `inventory/`: parsed source task inventory.
- `task_specs/<split>/*.bddl`: generated BDDL task specs.
- `manifests/*_tasks.jsonl`: generated task metadata and provenance.
- `seeds/canonical_episodes.json`: deterministic source episode mapping for smoke/eval.

## Frozen Benchmark Identity

- name: `libero90_generated_v1_envfiltered_304`
- source generator commit: `00150b2`
- source run: `libero_generated_envfiltered_inspire_20260904_r2_predicatecheck`
- env/runtime filter: generated candidates must reset and pass `env.check_success()`
- env/runtime filter result: `304/362` kept, `58` rejected
- final split: `3 smoke / 256 train / 45 validation`
- relative-place template: disabled for v1 stability
