"""Run a frozen oracle entrypoint while recording recovery RGB-D inputs.

Set ORACLE_ENTRYPOINT and ANCHOR_CAPTURE_DIR. Keep the frozen repository first
on PYTHONPATH; put this script and the two sensor modules in a separate directory
with an ``anchor_sensor`` package. Runner arguments pass through unchanged.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path
import runpy

from anchor_sensor.libero_rgbd_sensor import capture_libero_rgbd
from anchor_sensor.rgbd_observation import save_observation
from experiments.robot.libero.skill_pipeline import runner
from experiments.robot.libero.tiptop_repro import cutamp_controller_v2 as controller

OUT = Path(os.environ["ANCHOR_CAPTURE_DIR"])
OUT.mkdir(parents=True, exist_ok=True)
RECOVERY = 0
ATTEMPT = 0


def capture(env, obs, language, phase):
    before = hashlib.sha256(env.sim.get_state().flatten().tobytes()).hexdigest()
    step = env._anchor_control_steps
    directory = OUT / f"recovery{RECOVERY:02d}" / phase
    directory.mkdir(parents=True, exist_ok=False)
    for camera in ("agentview", "robot0_eye_in_hand"):
        frame = capture_libero_rgbd(
            env, obs, episode_id="task04_ep00", env_step=step, camera_id=camera
        )
        save_observation(frame, directory / camera)
    after = hashlib.sha256(env.sim.get_state().flatten().tobytes()).hexdigest()
    audit = dict(phase=phase, control_steps=step, language=language,
                 timestamp_s=float(env.sim.data.time),
                 physics_state_before=before, physics_state_after=after,
                 physics_unchanged=before == after)
    (directory / "capture_audit.json").write_text(json.dumps(audit, indent=2))
    if before != after:
        raise RuntimeError("RGB-D capture advanced or changed physics")


def get_env(task, resolution, seed):
    from libero.libero.envs import OffScreenRenderEnv
    env = OffScreenRenderEnv(bddl_file_name=str(task.bddl_path),
                             camera_heights=resolution, camera_widths=resolution,
                             camera_depths=True)
    env.seed(seed)
    env._anchor_control_steps = 0
    original_step = env.step

    @functools.wraps(original_step)
    def step(*args, **kwargs):
        result = original_step(*args, **kwargs)
        env._anchor_control_steps += 1
        return result

    env.step = step
    return env, task.language


original_recover = controller.CuTAMPV2TipTopController.recover
original_perceive = controller.CuTAMPV2OraclePerceiver.perceive


@functools.wraps(original_recover)
def recover(self, env, obs, task_description, *args, **kwargs):
    global RECOVERY, ATTEMPT
    RECOVERY += 1
    ATTEMPT = 0
    capture(env, obs, task_description, "entry")
    if os.environ.get('ANCHOR_SAVE_REPLAY_FIXTURE') == '1':
        import numpy as np
        from dataclasses import asdict
        fixture = OUT.parent / 'replay_fixture'
        fixture.mkdir(exist_ok=False)
        np.save(fixture / 'initial_physics_state.npy', env.sim.get_state().flatten())
        config = asdict(self.cfg)
        config.pop('llm_cfg', None)
        hints = kwargs.get('recovery_hints')
        (fixture / 'config.json').write_text(json.dumps(dict(controller_config=config,
            recovery_hints=hints, language=task_description, control_steps=env._anchor_control_steps,
            purpose='benchmark_initial_state_only; not_perception_input'), indent=2))
    return original_recover(self, env, obs, task_description, *args, **kwargs)


@functools.wraps(original_perceive)
def perceive(self, env, obs, task_description, *args, **kwargs):
    global ATTEMPT
    ATTEMPT += 1
    capture(env, obs, task_description, f"pre_solver_attempt{ATTEMPT:02d}")
    return original_perceive(self, env, obs, task_description, *args, **kwargs)


runner._get_libero_env = get_env
controller.CuTAMPV2TipTopController.recover = recover
controller.CuTAMPV2OraclePerceiver.perceive = perceive
if os.environ.get("ANCHOR_DIAGNOSTIC_HOOK"):
    runpy.run_path(os.environ["ANCHOR_DIAGNOSTIC_HOOK"], run_name="anchor_diagnostic_hook")
runpy.run_path(os.environ["ORACLE_ENTRYPOINT"], run_name="__main__")
