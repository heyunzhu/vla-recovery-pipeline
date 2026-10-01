"""Process-local import guard for named oracle modules in the dry-run canary."""

import importlib.abc
import sys


FORBIDDEN_MODULES = (
    "experiments.robot.libero.tiptop_repro.scene_reader",
    "experiments.robot.libero.tiptop_repro.cutamp_controller_v2",
    "experiments.robot.libero.tiptop_repro.libero_tiptop_executor",
)


class OracleImportGuard(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.blocked_import_attempts = 0

    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in FORBIDDEN_MODULES):
            self.blocked_import_attempts += 1
            raise ImportError("oracle module forbidden in visual dry-run: " + fullname)
        return None

    def __enter__(self):
        if any(name in sys.modules for name in FORBIDDEN_MODULES):
            raise RuntimeError("oracle modules were imported before the visual guard")
        sys.meta_path.insert(0, self)
        return self

    def __exit__(self, *args):
        sys.meta_path.remove(self)
