import unittest
import numpy as np
from scripts.recovery.skill_pipeline.diagnose_wrist_candidate_groups import overlap_components, overlap_record, projected_hits, link_strength


class WristCandidateGroupsTests(unittest.TestCase):
    def test_transitive_overlap_is_ambiguity_component(self):
        a=np.array([[1,1,0,0]],bool);b=np.array([[0,1,1,0]],bool);c=np.array([[0,0,1,1]],bool)
        self.assertEqual(overlap_components([a,b,c]),[[0,1,2]])
        self.assertEqual(overlap_components([a,c]),[[0],[1]])
        self.assertEqual(overlap_components([]),[])

    def test_dominance_is_not_verification(self):
        mask=np.ones((1,100),bool);gripper=mask.copy();gripper[0,-2:]=False
        row=overlap_record(mask,gripper,.98)
        self.assertTrue(row['offline_quarantine']);self.assertEqual(row['remaining_pixels'],2)
        for k in ('category_verified','identity_verified','planning_allowed','execution_allowed'):self.assertFalse(row[k])
        self.assertFalse(overlap_record(mask,gripper,.995)['offline_quarantine'])

    def test_projection_counts_sources_and_unique_destinations_separately(self):
        evidence={'status':np.array([[5,5,6]],np.uint8),'destination_uv':np.array([[[0,0],[0,0],[1,0]]])}
        row=projected_hits(np.ones((1,3),bool),np.array([[True,False]]),evidence)
        self.assertEqual(row,dict(consistent_source_points=2,source_points_hitting_destination_mask=2,unique_destination_pixels_hit=1))

    def test_bad_masks_and_thresholds_are_rejected(self):
        with self.assertRaises(ValueError):overlap_components([np.zeros((2,2),bool)])
        with self.assertRaises(ValueError):overlap_components([np.ones((2,2),bool),np.ones((1,2),bool)])
        with self.assertRaises(ValueError):overlap_record(np.ones((2,2),bool),np.ones((1,2),bool))
        with self.assertRaises(ValueError):overlap_record(np.ones((2,2),bool),np.ones((2,2),bool),np.nan)

    def test_small_boundary_hits_do_not_pass_strength_gate(self):
        weak=dict(consistent_source_points=1000,source_points_hitting_destination_mask=3,unique_destination_pixels_hit=3)
        strong=dict(consistent_source_points=1000,source_points_hitting_destination_mask=980,unique_destination_pixels_hit=500)
        self.assertFalse(link_strength(weak,strong)['diagnostic_strength_gate_passed'])
        self.assertTrue(link_strength(strong,strong)['diagnostic_strength_gate_passed'])
        duplicate=dict(consistent_source_points=1000,source_points_hitting_destination_mask=980,unique_destination_pixels_hit=1)
        self.assertFalse(link_strength(duplicate,strong)['diagnostic_strength_gate_passed'])


if __name__=='__main__':unittest.main()
