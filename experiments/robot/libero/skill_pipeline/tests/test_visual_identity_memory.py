import unittest
from dataclasses import replace

from experiments.robot.libero.skill_pipeline.tests.test_visual_temporal_diagnostics import sample
from experiments.robot.libero.skill_pipeline.visual_identity_memory import VisualIdentityMemory


def example(index):
    frame, handoff = sample(index)
    reference = replace(handoff.visible_objects[-1], id='obj_999', category='ramekin')
    handoff = replace(handoff,
        task_language='pick up the black bowl between the plate and the ramekin and place it on the plate',
        visible_objects=handoff.visible_objects + (reference,),
        binding=replace(handoff.binding, reference_ids=(handoff.binding.goal_id, 'obj_999'),
                        unverified_descriptors=('black bowl',), evidence={'initial_between': True}))
    return frame, handoff


class IdentityMemoryTest(unittest.TestCase):
    def test_initial_relation_is_not_reapplied_after_motion_or_reference_loss(self):
        memory = VisualIdentityMemory()
        initial = memory.observe(*example(0))
        frame, handoff = example(1)
        target = handoff.binding.target_id
        objects = tuple(replace(o, visible_centroid_world_m=(0.4, 0.0, 1.05)) if o.id == target else o
                        for o in handoff.visible_objects if o.id != 'obj_999')
        handoff = replace(handoff, status='binding_refused', reason='target_not_between',
                          binding=replace(handoff.binding, status='refused', target_id=None, goal_id=None),
                          visible_objects=objects)
        result = memory.observe(frame, handoff)
        self.assertEqual(result['status'], 'current_ids_candidate')
        self.assertEqual(result['remembered_target_id'], initial['remembered_target_id'])
        self.assertEqual(result['currently_missing_reference_ids'], ['obj_999'])
        self.assertEqual(result['unverified_descriptors'], ['black bowl'])
        for key in ('identity_continuity_verified', 'holding_verified', 'goal_verified', 'planning_allowed', 'execution_allowed'):
            self.assertFalse(result[key])

    def test_missing_target_does_not_select_distractor_and_reappearance_stays_unverified(self):
        memory = VisualIdentityMemory()
        initial = memory.observe(*example(0))
        frame, handoff = example(1)
        target = handoff.binding.target_id
        objects = tuple(replace(o, validity='not_observed', identity_status='history_only') if o.id == target else o
                        for o in handoff.visible_objects)
        distractor = replace(handoff.visible_objects[0], id='obj_777')
        result = memory.observe(frame, replace(handoff, visible_objects=objects + (distractor,),
                                              binding=replace(handoff.binding, target_id='obj_777')))
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['remembered_target_id'], initial['remembered_target_id'])
        self.assertFalse(result['current_target_observed'])
        recovered = memory.observe(*example(2))
        self.assertEqual(recovered['status'], 'reacquisition_candidate')
        self.assertTrue(recovered['requires_identity_reverification'])
        self.assertFalse(recovered['identity_continuity_verified'])

    def test_scene_conflict_breaks_continuity(self):
        memory = VisualIdentityMemory()
        memory.observe(*example(0))
        frame, handoff = example(1)
        result = memory.observe(frame, replace(handoff, status='scene_refused', binding=None,
                                               visible_objects=(), perception_backend_id=None))
        self.assertEqual(result['reason'], 'current_scene_refused')
        self.assertFalse(result['current_goal_observed'])
        self.assertEqual(memory.observe(*example(2))['status'], 'reacquisition_candidate')

    def test_failed_first_selection_cannot_seed_after_actions_without_reset(self):
        memory = VisualIdentityMemory()
        frame, handoff = example(0)
        memory.observe(frame, replace(handoff, status='binding_refused', binding=None))
        result = memory.observe(*example(1))
        self.assertEqual(result['reason'], 'initial_binding_unavailable_reset_required')
        self.assertIsNone(result['remembered_target_id'])
        memory.reset()
        self.assertEqual(memory.observe(*example(1))['status'], 'initial_candidate')

    def test_category_drift_new_identity_and_insufficient_depth_are_unknown(self):
        for changes in ({'category': 'ramekin'}, {'identity_status': 'new'}, {'depth_valid_fraction': 0.7}):
            memory = VisualIdentityMemory()
            memory.observe(*example(0))
            frame, handoff = example(1)
            objects = tuple(replace(o, **changes) if o.id == handoff.binding.target_id else o for o in handoff.visible_objects)
            self.assertEqual(memory.observe(frame, replace(handoff, visible_objects=objects))['status'], 'unknown')

    def test_cached_evidence_is_immutable_and_changes_are_rejected(self):
        memory = VisualIdentityMemory()
        frame, handoff = example(0)
        result = memory.observe(frame, handoff)
        result['unverified_descriptors'].clear()
        self.assertEqual(memory.observe(frame, handoff)['unverified_descriptors'], ['black bowl'])
        with self.assertRaisesRegex(ValueError, 'cached frame'):
            memory.observe(frame, replace(handoff, reason='changed'))
        with self.assertRaisesRegex(ValueError, 'RGB-D frame'):
            memory.observe(frame, replace(handoff, frame_rgb_sha256='wrong'))
        with self.assertRaisesRegex(ValueError, 'inconsistent scene'):
            memory.observe(frame, replace(handoff, mask_conflicts=({'reason': 'overlap'},)))

    def test_context_backend_calibration_and_time_changes_require_reset(self):
        for change in ('language', 'backend', 'calibration', 'timestamp'):
            memory = VisualIdentityMemory()
            memory.observe(*example(0))
            frame, handoff = example(1)
            if change == 'language':
                handoff = replace(handoff, task_language='different task')
            elif change == 'backend':
                handoff = replace(handoff, perception_backend_id='different detector')
            elif change == 'calibration':
                K = frame.K.copy(); K[0, 0] += 1
                frame = replace(frame, K=K)
            else:
                frame = replace(frame, timestamp_s=0.0)
                handoff = replace(handoff, timestamp_s=0.0)
            with self.assertRaises(ValueError):
                memory.observe(frame, handoff)
