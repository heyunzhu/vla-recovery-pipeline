# Native Grounding DINO, original 8-class experiment

Best checkpoint: `best_coco_bbox_mAP_epoch_5.pth` (Git LFS),
693,373,018 bytes, SHA256
`12c97487fc59fcbf1da38b081c941e6024fa4f8af0c02e0e31cbc308c87b96b6`.

Classes in order: wine bottle, bowl, plate, basket, rack, cream cheese, milk,
orange juice. `config.py` is the original MMDetection training configuration;
`calibration.json` contains validation calibration, not a test-derived threshold.
Absolute BERT/data/output paths refer to the original server and must be mapped
to the restored environment. The complete dataset, training records and source
snapshots are indexed in `archives/ssh_20261018/archive_index.json`.

This is the historical 8-class baseline. The later 19-class native model is
stored separately in `models/rgbd_dino_full_20261018/`. Preserve model identity,
class order and calibration together when comparing them.
