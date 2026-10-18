import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_collision_policy import hard_obstacle_mask


class VisualCollisionPolicyTest(unittest.TestCase):
    def masks(self):
        masks=np.zeros((4,5,5),bool)
        for i in range(4):masks[i,i,i]=True
        return masks,['bowl','rack','bottle','cheese']

    def test_default_keeps_all_labeled_instances(self):
        masks,categories=self.masks();hard,removed,r=hard_obstacle_mask(masks,categories)
        np.testing.assert_array_equal(hard,masks.any(0));self.assertFalse(removed.any())

    def test_explicit_policy_removes_only_bound_contact_instances(self):
        masks,categories=self.masks();hard,removed,r=hard_obstacle_mask(masks,categories,policy='oracle_cheese_rack_contacts_v1')
        np.testing.assert_array_equal(hard,masks[2:].any(0));np.testing.assert_array_equal(removed,masks[:2].any(0))
        self.assertEqual([x['category'] for x in r['excluded_instances']],['bowl','rack'])
        self.assertFalse(r['oracle_object_state_used'])

    def test_ambiguous_or_missing_instance_cannot_silently_align_policy(self):
        masks,categories=self.masks()
        for cats in [['bowl','bowl','bottle','cheese'],['plate','rack','bottle','cheese']]:
            with self.assertRaisesRegex(ValueError,'requires one visible'):
                hard_obstacle_mask(masks,cats,policy='oracle_cheese_rack_contacts_v1')

    def test_overlap_with_hard_object_is_preserved(self):
        masks,categories=self.masks();masks[2,0,0]=True
        hard,removed,r=hard_obstacle_mask(masks,categories,policy='oracle_cheese_rack_contacts_v1')
        self.assertTrue(hard[0,0]);self.assertFalse(removed[0,0]);self.assertEqual(r['overlap_retained_pixels'],1)


if __name__=='__main__':unittest.main()
