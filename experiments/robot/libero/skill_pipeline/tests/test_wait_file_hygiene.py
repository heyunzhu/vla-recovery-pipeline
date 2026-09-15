"""The mining lane must not leave a consumed WAIT_CODEX.json behind.

A finished run used to keep the wait file and its ``wait_codex`` status forever,
which made finished runs indistinguishable from runs that really wait for a
draft -- and that is exactly what the intervention watcher gates on.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.robot.libero.skill_pipeline.mine import (
    clear_consumed_wait_file,
    load_mine_state,
    save_mine_state,
)


def _state(*, awaiting_task: int | None, awaiting_kind: str | None) -> dict:
    return {
        "completed": [],
        "awaiting_task": awaiting_task,
        "awaiting_kind": awaiting_kind,
        "tasks": {"5": {"status": "awaiting_draft" if awaiting_kind == "draft" else "passed", "writes": 1}},
    }


class WaitFileHygieneTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        (root / "mine").mkdir(parents=True, exist_ok=True)
        state_path = root / "mine" / "mine_state.json"
        (root / "mine" / "WAIT_CODEX.json").write_text(json.dumps({"status": "need_draft"}), encoding="utf-8")
        return state_path

    def test_waiting_for_a_draft_keeps_the_wait_file(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            state_path = self._fixture(root)
            save_mine_state(state_path, _state(awaiting_task=5, awaiting_kind="draft"))
            self.assertTrue((root / "mine" / "WAIT_CODEX.json").exists())

    def test_pending_validation_removes_the_wait_file(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            state_path = self._fixture(root)
            save_mine_state(state_path, _state(awaiting_task=5, awaiting_kind="validation"))
            self.assertFalse((root / "mine" / "WAIT_CODEX.json").exists())

    def test_finished_run_removes_the_wait_file(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            state_path = self._fixture(root)
            save_mine_state(state_path, _state(awaiting_task=None, awaiting_kind=None))
            self.assertFalse((root / "mine" / "WAIT_CODEX.json").exists())
            # The state file itself must still be written.
            state = load_mine_state(state_path)
            self.assertIsNone(state["awaiting_task"])

    def test_missing_wait_file_is_not_an_error(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            (root / "mine").mkdir(parents=True)
            state_path = root / "mine" / "mine_state.json"
            save_mine_state(state_path, _state(awaiting_task=None, awaiting_kind=None))
            self.assertFalse(clear_consumed_wait_file(state_path, _state(awaiting_task=None, awaiting_kind=None)))
            self.assertTrue(state_path.exists())


if __name__ == "__main__":
    unittest.main()
