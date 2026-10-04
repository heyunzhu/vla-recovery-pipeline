"""Offline identity-memory diagnostics; remembered IDs are not observations."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json

import numpy as np

from .perception_artifact import rgb_sha256
from .rgbd_scene_provider import _frame_digest


class VisualIdentityMemory:
    """Freeze the first provisional task selection; never select a replacement.

    This is separate from the production adapter. Tracker IDs and visible
    centroids are weak evidence, not verified physical identity or attachment.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self._context = self._backend = self._calibration = None
        self._seed = self._key = self._digest = self._result = None
        self._attempted_seed = self._interrupted = False
        self._timestamp = None

    @staticmethod
    def _eligible(obj, step, *, require_tracked):
        return (obj is not None and obj.validity == 'observed' and obj.last_seen_step == step
                and obj.identity_status in ({'tracked'} if require_tracked else {'new', 'tracked'})
                and obj.category is not None and obj.id.startswith('obj_')
                and obj.visible_centroid_world_m is not None
                and np.asarray(obj.visible_centroid_world_m).shape == (3,)
                and np.isfinite(obj.visible_centroid_world_m).all()
                and obj.depth_valid_fraction is not None and 0.8 <= obj.depth_valid_fraction <= 1
                and obj.detection_index is not None and obj.detection_mask_sha256 is not None)

    def observe(self, frame, handoff):
        snapshot = f'{frame.episode_id}:step{frame.env_step}:{frame.camera_id}'
        if (handoff.snapshot_id != snapshot or handoff.source != 'rgbd'
                or handoff.episode_id != frame.episode_id or handoff.env_step != frame.env_step
                or handoff.camera_id != frame.camera_id or handoff.timestamp_s != frame.timestamp_s
                or handoff.calibration_version != frame.calibration_version
                or handoff.frame_rgb_sha256 != rgb_sha256(frame)
                or handoff.robot_state != dict(frame.robot_state)):
            raise ValueError('identity memory handoff does not match RGB-D frame')
        if (handoff.status not in {'visual_id_candidate', 'binding_refused', 'scene_refused'}
                or (handoff.status == 'scene_refused' and (handoff.visible_objects or handoff.binding is not None))
                or (handoff.status != 'scene_refused' and handoff.mask_conflicts)):
            raise ValueError('identity memory received inconsistent scene admission')
        context = (frame.episode_id, frame.camera_id, handoff.task_language)
        calibration = (frame.calibration_version, frame.K.tobytes(), frame.T_world_camera.tobytes())
        if self._context is not None and context != self._context:
            raise ValueError('reset identity memory before changing episode/camera/language')
        if self._calibration is not None and calibration != self._calibration:
            raise ValueError('reset identity memory after camera calibration changes')
        if (self._backend is not None and handoff.perception_backend_id is not None
                and handoff.perception_backend_id != self._backend):
            raise ValueError('reset identity memory before changing detector backend')
        key = (frame.episode_id, frame.env_step, frame.camera_id)
        digest = (_frame_digest(frame), hashlib.sha256(json.dumps(
            dataclasses.asdict(handoff), sort_keys=True, allow_nan=False).encode()).digest())
        if key == self._key:
            if digest != self._digest:
                raise ValueError('identity memory evidence changed for cached frame')
            return copy.deepcopy(self._result)
        if self._key is not None and (frame.env_step <= self._key[1] or frame.timestamp_s <= self._timestamp):
            raise ValueError('identity memory requires increasing steps and timestamps')
        self._context, self._calibration = context, calibration
        if handoff.perception_backend_id is not None:
            self._backend = handoff.perception_backend_id
        result = dict(snapshot_id=snapshot, source='offline_initial_task_identity_memory',
            status='unknown', reason=None, remembered_target_id=None, remembered_goal_id=None,
            current_target_observed=False, current_goal_observed=False,
            initial_snapshot_id=None, initial_selector_evidence=None,
            unverified_descriptors=[], currently_missing_reference_ids=[],
            requires_identity_reverification=self._interrupted,
            identity_continuity_verified=False, holding_verified=False, goal_verified=False,
            planning_allowed=False, execution_allowed=False)
        objects = {obj.id: obj for obj in handoff.visible_objects}
        if len(objects) != len(handoff.visible_objects):
            raise ValueError('identity memory received duplicate scene IDs')
        if not self._attempted_seed:
            self._attempted_seed = True
            binding = handoff.binding
            target = objects.get(binding.target_id) if binding else None
            goal = objects.get(binding.goal_id) if binding else None
            if (handoff.status == 'visual_id_candidate' and binding is not None
                    and binding.snapshot_id == snapshot and binding.source == 'task_language_rgbd_scene'
                    and binding.status in {'bound_ids', 'candidate_requires_attribute_check'}
                    and self._eligible(target, frame.env_step, require_tracked=False)
                    and self._eligible(goal, frame.env_step, require_tracked=False) and target.id != goal.id):
                self._seed = dict(binding=copy.deepcopy(binding), target_category=target.category,
                                  goal_category=goal.category, timestamp=frame.timestamp_s)
                result.update(status='initial_candidate', current_target_observed=True, current_goal_observed=True)
            else:
                result['reason'] = 'initial_binding_unavailable_reset_required'
        elif self._seed is None:
            result['reason'] = 'initial_binding_unavailable_reset_required'
        elif handoff.status == 'scene_refused':
            result['reason'] = 'current_scene_refused'
            self._interrupted = True
        else:
            binding = self._seed['binding']
            target, goal = objects.get(binding.target_id), objects.get(binding.goal_id)
            target_ok = (self._eligible(target, frame.env_step, require_tracked=True)
                         and target.category == self._seed['target_category'])
            goal_ok = (self._eligible(goal, frame.env_step, require_tracked=True)
                       and goal.category == self._seed['goal_category'])
            result.update(current_target_observed=target_ok, current_goal_observed=goal_ok)
            if not target_ok or not goal_ok:
                result['reason'] = 'remembered_target_or_goal_not_currently_observed_and_tracked'
                self._interrupted = True
            else:
                if not 0 < frame.timestamp_s - self._timestamp <= 0.5:
                    self._interrupted = True
                result['status'] = 'reacquisition_candidate' if self._interrupted else 'current_ids_candidate'
                result['reason'] = 'identity_reverification_required' if self._interrupted else None
        if self._seed is not None:
            binding = self._seed['binding']
            result.update(remembered_target_id=binding.target_id, remembered_goal_id=binding.goal_id,
                initial_snapshot_id=binding.snapshot_id, initial_selector_evidence=copy.deepcopy(binding.evidence),
                unverified_descriptors=list(binding.unverified_descriptors),
                currently_missing_reference_ids=[identity for identity in binding.reference_ids
                    if not self._eligible(objects.get(identity), frame.env_step, require_tracked=False)],
                requires_identity_reverification=self._interrupted)
        self._key, self._digest, self._timestamp, self._result = key, digest, frame.timestamp_s, result
        return copy.deepcopy(result)
