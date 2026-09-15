# TiPToP V2 Prototype Notes

This version keeps oracle simulator perception but splits the recovery system
into replaceable modules.

## Modules

- `OracleScenePerceiver`: reads simulator truth and builds an object-centric
  scene graph.
- `RuleTaskPlanner`: emits a symbolic recovery plan from predicates.
- `check_plan`: verifies simple feasibility constraints before execution.
- `execute_plan`: runs short scripted skills.
- `HumanFallback`: records when the hierarchy would ask a human for help.
- `TipTopRecoveryController`: closes the loop by perceiving, planning,
  checking, executing, re-perceiving, replanning, and falling back to human.

## Current Flow

```text
VLA trigger
-> oracle perception
-> scene graph
-> symbolic rule planner
-> feasibility check
-> skill execution
-> replan if needed
-> human fallback if infeasible or budget exhausted
```

The important boundary is `TipTopRecoveryController.recover(env, obs,
task_description)`. It returns the new observation, success flag, total recovery
steps, all plan attempts, and human fallback metadata.

## What Is Still Simplified

- Perception is still simulator truth, not image-based recognition.
- Planning is still rule/template based, not VLM-generated.
- Feasibility checks are geometric sanity checks, not full motion planning.
- Human fallback is logging-only and does not block evaluation.
