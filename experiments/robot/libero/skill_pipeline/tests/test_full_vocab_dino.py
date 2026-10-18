from pathlib import Path
import json,tempfile,unittest
from scripts.recovery.skill_pipeline.train_grounding_dino_libero import dataset_classes
from scripts.recovery.skill_pipeline.run_full_vocab_dino_experiment import finalize_dataset
from scripts.recovery.skill_pipeline.validate_full_vocab_dino_experiment import compare_outputs


class FullVocabularyTests(unittest.TestCase):
    def test_export_matching_requires_same_image_and_class(self):
        first=[dict(image_id=1,category_id=1,bbox=[0,0,20,20],score=.9)]
        second=[dict(first[0],category_id=2)]
        self.assertFalse(compare_outputs(first,second)['passed'])
        self.assertTrue(compare_outputs(first,[dict(first[0],score=.901)])['passed'])
        self.assertFalse(compare_outputs(first,[dict(first[0],score=.95)])['passed'])

    def test_dynamic_vocabulary_and_split_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'annotations').mkdir()
            cats=[dict(id=i+1,name='class '+str(i)) for i in range(19)]
            for split in ['train','val','test']:(root/'annotations'/f'{split}640.json').write_text(json.dumps(dict(categories=cats)))
            self.assertEqual(len(dataset_classes(root)),19)
            (root/'annotations/test640.json').write_text(json.dumps(dict(categories=[dict(id=1,name='different')]+cats[1:])))
            with self.assertRaisesRegex(ValueError,'mappings differ'):dataset_classes(root)

    def test_identical_pixels_do_not_cross_splits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'logs/run';run.mkdir(parents=True)
            data=root/'datasets/rgbd_dino_full_20261018';data.mkdir(parents=True)
            (run/'taxonomy.json').write_text(json.dumps(dict(classes=['bowl'])))
            records=[('a','train','layout_a','same'),('b','test','layout_b','same'),('c','train','layout_c','other'),('d','val','layout_d','third')]
            for i,(episode,split,layout,pixels) in enumerate(records):
                case=run/'collection'/episode;case.mkdir(parents=True);(case/'complete.json').write_text('{}')
                row=dict(id=i+1,episode=episode,split=split,layout_group=layout,pixel_sha256=pixels,phase='skill_trigger',camera='agentview',file_name=episode+'.png',annotations=[dict(category_id=1,bbox=[0,0,10,10],area=100,iscrowd=0)])
                (case/'frames.jsonl').write_text(json.dumps(row)+'\n')
            result=finalize_dataset(root,run)
            self.assertEqual(result['split_statistics']['train']['images'],1)
            self.assertEqual(result['excluded'][0]['reason'],'cross_split_physical_or_rgb_duplicate')
            train=json.loads((data/'annotations/train640.json').read_text())
            test=json.loads((data/'annotations/test640.json').read_text())
            self.assertFalse({r['pixel_sha256'] for r in train['images']} & {r['pixel_sha256'] for r in test['images']})


if __name__=='__main__':unittest.main()
