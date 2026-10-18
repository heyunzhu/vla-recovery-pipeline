"""Exercise the capture bridge without importing its executable entrypoint."""
import ast
import functools
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class AnchorCaptureHelpersTest(unittest.TestCase):
    def test_runner_episode_reseed_replaces_base_seed_and_actions_pass_through(self):
        root = Path(__file__).resolve().parents[5]
        source = root / "scripts/recovery/skill_pipeline/capture_oracle_recovery_rgbd.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_env")
        class FakeEnvironment:
            def __init__(self, **kwargs): self.seeds = []; self.actions = []
            def seed(self, value): self.seeds.append(value)
            def step(self, action):
                self.actions.append(action)
                return {"measurement": 1}, 0., False, {}
        modules = {name: ModuleType(name) for name in ("libero", "libero.libero", "libero.libero.envs")}
        modules["libero.libero.envs"].OffScreenRenderEnv = FakeEnvironment
        namespace = dict(functools=functools, os=os)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        with patch.dict(sys.modules, modules):
            env, language = namespace["get_env"](SimpleNamespace(bddl_path="example.bddl", language="task"), 256, 90)
        env.seed(2)
        self.assertEqual(env.seeds, [90, 2])
        self.assertEqual(env._anchor_episode_seed, 2)
        self.assertEqual(language, "task")
        action = object()
        self.assertEqual(env.step(action), ({"measurement": 1}, 0., False, {}))
        self.assertIs(env.actions[0], action)
        self.assertEqual(env._anchor_control_steps, 1)

if __name__ == "__main__": unittest.main()
