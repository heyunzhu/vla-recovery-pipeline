"""Shared diagnostic interfaces; no oracle scene type or action authorization."""

from __future__ import annotations

from .rgbd_scene_provider import RGBDSceneProvider
from .visual_recovery_handoff import build_visual_recovery_handoff


class VisualDryRunAdapter:
    def __init__(self, provider: RGBDSceneProvider):
        self.provider = provider
        self._key = None
        self._language = None
        self._handoff = None

    def reset(self):
        self.provider.reset()
        self._key = self._language = self._handoff = None

    def _read(self, frame, language):
        # Always check the frame digest, including cached requests.
        admission = self.provider.get_admission(frame)
        key = (frame.episode_id, frame.env_step, frame.camera_id)
        if key == self._key:
            if language != self._language:
                raise ValueError("task language changed for cached visual decision")
            return self._handoff
        handoff = build_visual_recovery_handoff(language, frame, admission)
        self._key, self._language, self._handoff = key, language, handoff
        return handoff

    def query_state(self, frame, language):
        return self._read(frame, language)

    def perceive(self, frame, language):
        return self._read(frame, language)

    def executor_scene(self, frame, language):
        return self._read(frame, language)

    def require_action_authorization(self, frame, language):
        handoff = self._read(frame, language)
        raise PermissionError("visual dry-run forbids planning and execution: " + handoff.status)
