# TiPToP-Style LIBERO Recovery Prototype

This directory contains a first-pass TiPToP-style recovery stack for LIBERO.
It keeps perception grounded in simulator state for now, then builds an
object-centric scene, symbolic predicates, a recovery plan skeleton, simple
continuous feasibility checks, and short scripted primitives.

The first goal is not to reproduce cuTAMP/curobo exactly. The goal is to make
the system boundary explicit:

1. VLA runs normally.
2. The existing uncertainty forecaster triggers recovery.
3. The scene reader converts simulator truth into object-centric state.
4. The planner emits a symbolic plan such as `retreat_open -> regrasp -> place`.
5. The executor runs short motion primitives and returns control to VLA.
