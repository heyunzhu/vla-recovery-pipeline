# Task06 Mining Findings

Pack: `libero_goal_task_task06_fresh_manual_20260912_235650`

Task: `libero_goal_task` task06, `Push the cream cheese to the front of the stove`

BDDL goal atom: `on(cream_cheese_1_main, main_table_stove_front_region)`

## Evidence Summary

- Baseline seed 51 with an empty strict pack reached `1/15` success and did not trigger recovery.
- Forced q20 recovery with an empty strict pack built a wrong required final atom: `on(cream_cheese_1_main, flat_stove_1_main)`. This showed a grounding failure: the phrase `front of the stove` was bound to the stove body instead of the BDDL table-front region.
- The grounding hint in this pack rewrites that misbinding to `main_table_stove_front_region` when the task language, target object, and BDDL goal surface match task06.
- The geometry hint in this pack registers `main_table_stove_front_region` from the BDDL bounds as a virtual fixed table rectangle, so the planner sees a concrete table-front support surface.
- Forced q20 recovery with the new hints built the intended recovery goal: `on(cream_cheese_1_main, main_table_stove_front_region), handempty`, with `target_support_surfaces` including `main_table_stove_front_region`.
- Despite the corrected goal and virtual surface, cuTAMP still returned no executable plan. The repeated blockers were `KinematicConstraint.pos_err` and `Collision.robot_to_world`.
- A q0 forced-recovery run reached one overall success, but trace inspection showed recovery itself failed first; the later VLA continuation pushed the object into the goal region. This is not evidence for admitting a repair trigger.

## Decision

Do not admit a repair trigger for this pack.

The mined capability fixes a real grounding/geometry bug, but it does not make the current recovery backend solve the task. A repair trigger would route episodes into an infeasible pick/place recovery and can reduce the chance that the VLA policy finishes the push on its own.

The next useful capability would be a supported push or nudge recovery primitive for small table objects, or an executor path that can deliberately slide the object along the table into a BDDL region. That primitive is not present in the current pack-local capability surface.

## Verification Artifacts

- Pack code check: `python -m experiments.robot.libero.skill_pipeline.pack_code_check skill_packs/libero_goal_task_task06_fresh_manual_20260912_235650` returned `PASS` after the final pack edits.
- Baseline summary: `logs/libero_goal_task_task06_fresh_manual_20260912_235650/baseline_task06_seed51_65_cleanpack/summary.json`, success rate `0.0667`.
- Empty-pack q20 forced recovery: `logs/libero_goal_task_task06_fresh_manual_20260912_235650/force_q20_task06_seed51_3_empty_pack/summary.json`, success rate `0.0`.
- Region-hint q20 forced recovery: `logs/libero_goal_task_task06_fresh_manual_20260912_235650/force_q20_task06_seed51_3_region_hints_v1/summary.json`, success rate `0.0`.
- Region-hint q20 cutamp diagnosis: `logs/libero_goal_task_task06_fresh_manual_20260912_235650/force_q20_task06_seed51_3_region_hints_v1/cutamp_diagnosis.json`, `0/6` feasible solves; zero-satisfying constraints were `Collision.robot_to_world` and `KinematicConstraint.pos_err` in all six solves.
- Region-hint q0 forced recovery: `logs/libero_goal_task_task06_fresh_manual_20260912_235650/force_q0_task06_seed51_3_region_hints_v1/summary.json`, success rate `0.3333`; trace inspection showed the recovery plan itself was infeasible before VLA continuation succeeded.
- Region-hint q0 cutamp diagnosis: `logs/libero_goal_task_task06_fresh_manual_20260912_235650/force_q0_task06_seed51_3_region_hints_v1/cutamp_diagnosis.json`, `0/6` feasible solves with the same repeated blockers.
- Grounding quality gate: `logs/libero_goal_task_task06_fresh_manual_20260912_235650/quality_gate_grounding_final/skill_quality_gate_result.json`, `ok: true`, capability audit passed with no errors.
- Geometry quality gate: `logs/libero_goal_task_task06_fresh_manual_20260912_235650/quality_gate_geometry_final/skill_quality_gate_result.json`, `ok: true`, capability audit passed with no errors.
