---
id: libero90_top_drawer_open_hand_stall
name: Top drawer open-hand stall
kind: trigger
track: fail_only
hook: after_pi0_query
priority: 40
when_to_apply: In fail-only LIBERO-90 drawer-close rollouts, after the arm has approached the cabinet and the open empty hand has stopped making progress across several Pi0 query windows.
when_not_to_apply: Do not promote this draft to online use until task or drawer scope can be checked; the current executable trigger is intentionally conservative but too broad outside the fail-only draft library.
failure_signature:
  - The task is close the top drawer of the cabinet.
  - All writing rollouts run to the 400-step horizon with success=false.
  - The gripper stays open, with aperture roughly 0.033 to 0.041 m.
  - holding_status remains handempty_or_unconfirmed for every query.
  - The arm reaches the cabinet area and then stalls without a decisive drawer-closing interaction.
recovery_point: After approach, when the open empty hand first stalls near the cabinet for a short query window, before the episode spends the remaining horizon repeating VLA motion.
trigger:
  all:
    - aperture_gt: 0.03
    - holding_status_is: handempty_or_unconfirmed
    - ee_stalled:
        window: 6
        max_disp_m: 0.015
backend: cutamp_recover
evidence:
  tasks:
    - libero_90 task01 close the top drawer of the cabinet
  episodes:
    - task01_ep00_seed90
    - task01_ep01_seed90
    - task01_ep02_seed90
    - task01_ep03_seed90
    - task01_ep04_seed90
---

## Intent

This fail-only draft describes a repeatable VLA stall on LIBERO-90 task01. The online action, if this pattern is later promoted through pair validation, is not a new executor. The matched hook should enter the existing `cutamp_recover` backend, and cuTAMP should choose recovery goals from the current rule table.

## Evidence Summary

The five writing rollouts contain no recovery events. That is expected for this track: skills were disabled, so `recovery_trace.jsonl` exists but is empty. The useful evidence is the query timeline plus the fail-only keyframes.

The shared trace pattern is open gripper, empty hand, no confirmed object following, and repeated low-displacement query windows after the arm reaches the cabinet area. The contact sheet visually supports the same diagnosis: the arm approaches the drawer front and spends the rest of the rollout without a clear drawer-close push.

## Anti-Patterns

- Do not add this file to `_index.yaml` `online:`.
- Do not interpret this as a cuTAMP goal-writing skill; the rule table owns recovery goals.
- Do not add query index, seed, absolute xyz, contacts, or vision-only text to the executable trigger.
- Do not promote this while the trigger can only express generic open-hand stalling.

## Promotion Notes

Before promotion, run held-out fail-only task01 episodes and same-init off/on recovery. If the same broad stall trigger fires on unrelated successful tasks, add a scoped predicate first rather than weakening the evidence threshold.
