#!/usr/bin/env python3
"""Build a reproducible LIBERO detector config and run MMDetection training."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

CLASSES = ("wine bottle", "bowl", "plate", "basket", "rack", "cream cheese", "milk", "orange juice")


def dataset_classes(directory):
    reference = None
    for split in ("train", "val", "test"):
        categories = json.loads((directory / f"annotations/{split}640.json").read_text())["categories"]
        categories = sorted(categories, key=lambda c: c["id"])
        names = tuple(c["name"] for c in categories)
        if not names or len(set(names)) != len(names) or [c["id"] for c in categories] != list(range(1, len(names)+1)):
            raise ValueError("dataset categories must have unique names and contiguous one-based IDs")
        if reference is not None and names != reference:
            raise ValueError("category mappings differ between dataset splits")
        reference = names
    return reference


def build_config(args):
    from mmengine.config import Config
    source = args.mmdetection / "configs/grounding_dino/grounding_dino_swin-t_finetune_16xb2_1x_coco.py"
    cfg = Config.fromfile(str(source))
    cfg.custom_imports = dict(imports=["scripts.recovery.skill_pipeline.grounding_dino_finetune_components"], allow_failed_imports=False)
    classes = dataset_classes(args.dataset)
    cfg.model.bbox_head.num_classes = len(classes)
    cfg.model.language_model.name = str(args.bert)
    cfg.load_from = str(args.pretrained)
    cfg.work_dir = str(args.output)
    cfg.randomness = dict(seed=args.seed, deterministic=False)
    cfg.env_cfg.mp_cfg.opencv_num_threads = 0
    cfg.env_cfg.cudnn_benchmark = False
    taxonomy_path = args.dataset / "taxonomy.json"
    aliases = json.loads(taxonomy_path.read_text()).get("aliases", {}) if taxonomy_path.exists() else {}
    train_pipeline = [dict(type="LoadImageFromFile"),dict(type="LoadAnnotations",with_bbox=True),
        dict(type="RandomFlip",prob=.5),
        dict(type="RandomChoiceResize",scales=[(512,1333),(640,1333),(800,1333)],keep_ratio=True),
        dict(type="SampleTaskDetectionPrompt", aliases=aliases),
        dict(type="PackDetInputs",meta_keys=("img_id","img_path","ori_shape","img_shape","scale_factor","flip","flip_direction","text","custom_entities"))]
    test_pipeline = [dict(type="LoadImageFromFile"),dict(type="FixScaleResize",scale=(800,1333),keep_ratio=True),
        dict(type="LoadAnnotations",with_bbox=True),
        dict(type="PackDetInputs",meta_keys=("img_id","img_path","ori_shape","img_shape","scale_factor","text","custom_entities"))]
    for split in ("train", "val", "test"):
        dataset = dict(type="CocoDataset",data_root=str(args.dataset)+"/",metainfo=dict(classes=classes),
            ann_file=f"annotations/{split}640.json",data_prefix=dict(img=""),return_classes=True,
            filter_cfg=dict(filter_empty_gt=False,min_size=1),pipeline=train_pipeline if split=="train" else test_pipeline)
        loader = dict(batch_size=args.batch_size if split=="train" else 1,num_workers=args.workers,persistent_workers=args.workers>0,
            sampler=dict(type="DefaultSampler",shuffle=split=="train"),dataset=dataset,drop_last=False)
        cfg[f"{split}_dataloader"] = loader
    cfg.val_evaluator = dict(type="CocoMetric",ann_file=str(args.dataset/"annotations/val640.json"),metric="bbox",format_only=False)
    cfg.test_evaluator = dict(type="CocoMetric",ann_file=str(args.dataset/"annotations/test640.json"),metric="bbox",format_only=False)
    cfg.optim_wrapper = dict(type="OptimWrapper",accumulative_counts=args.accumulation,
        optimizer=dict(type="AdamW",lr=args.lr,weight_decay=.0001),
        clip_grad=dict(max_norm=.1,norm_type=2),
        paramwise_cfg=dict(custom_keys={"backbone":dict(lr_mult=.1),"language_model":dict(lr_mult=0)}))
    cfg.train_cfg = dict(type="EpochBasedTrainLoop",max_epochs=args.epochs,val_interval=1)
    cfg.param_scheduler = [dict(type="LinearLR",start_factor=.1,by_epoch=False,begin=0,end=50),
        dict(type="MultiStepLR",by_epoch=True,begin=0,end=args.epochs,milestones=[max(1,args.epochs-2)],gamma=.1)]
    cfg.default_hooks.checkpoint = dict(type="CheckpointHook",interval=1,max_keep_ckpts=2,save_best="coco/bbox_mAP",rule="greater")
    cfg.default_hooks.logger = dict(type="LoggerHook",interval=10)
    cfg.custom_hooks = [dict(type="FreezeDetectorLanguageHook")]
    cfg.auto_scale_lr = dict(enable=False,base_batch_size=args.batch_size)
    cfg.visualizer.vis_backends = [dict(type="LocalVisBackend")]
    cfg.launcher = "none"
    if args.smoke_iterations:
        cfg.train_cfg = dict(type="IterBasedTrainLoop",max_iters=args.smoke_iterations,val_interval=args.smoke_iterations+1)
        cfg.param_scheduler = []
        cfg.default_hooks.checkpoint = dict(type="CheckpointHook",by_epoch=False,interval=args.smoke_iterations,save_last=True,max_keep_ckpts=1)
        cfg.default_hooks.logger = dict(type="LoggerHook",interval=1)
    return cfg


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mmdetection",type=Path,required=True);p.add_argument("--dataset",type=Path,required=True)
    p.add_argument("--bert",type=Path,required=True);p.add_argument("--pretrained",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);p.add_argument("--epochs",type=int,default=12)
    p.add_argument("--batch-size",type=int,default=4);p.add_argument("--workers",type=int,default=4)
    p.add_argument("--lr",type=float,default=.00005);p.add_argument("--seed",type=int,default=20261015)
    p.add_argument("--accumulation",type=int,default=1);p.add_argument("--smoke-iterations",type=int,default=0)
    p.add_argument("--config-only",action="store_true");args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(args.mmdetection))
    cfg=build_config(args);cfg.dump(str(args.output/"config.py"))
    (args.output/"launch_manifest.json").write_text(json.dumps({"argv":sys.argv,"script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "dataset_audit":json.loads((args.dataset/"dataset_audit.json").read_text()),"pretrained":str(args.pretrained)},indent=2))
    if args.config_only:return
    from mmengine.utils import import_modules_from_strings
    import_modules_from_strings(**cfg.custom_imports)
    from mmengine.runner import Runner
    Runner.from_cfg(cfg).train()


if __name__=="__main__":main()
