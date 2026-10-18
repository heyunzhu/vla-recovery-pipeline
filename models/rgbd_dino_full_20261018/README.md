# 19-class native Grounding DINO checkpoint

The actual trained checkpoint is tracked with **Git LFS**, together with the training config, taxonomy and `manifest.json`. It is the validation-selected epoch-10 checkpoint, not a converted HF model. The file is preserved byte-for-byte from the selected training output; no private credentials are included.

```bash
git lfs install
git lfs pull --include="models/rgbd_dino_full_20261018/best_coco_bbox_mAP_epoch_10.pth"
sha256sum models/rgbd_dino_full_20261018/best_coco_bbox_mAP_epoch_10.pth
```

Expected size: **710647898 bytes**. Expected SHA256:

```text
735b0e3ca9f8a44ad97dbaec97d15c61f18248e01d3e1479d0556d50f3388edd
```

Native runtime used for reference inference: Python 3.10, PyTorch 2.1.2+cu121, MMCV 2.1.0, MMEngine 0.10.7, MMDetection 3.3.0, Transformers 4.40.2. The repository's generic runtime dependencies do not replace this isolated environment. MMDetection source and its compiled MMCV operators must be available on the target machine.

`training_config.py` preserves original training paths. For inference, point `model.language_model.name` at a local `bert-base-uncased` directory, as in the benchmark setup script. The base BERT files, SAM2 model and VLA policy are external dependencies and are not duplicated in this checkpoint directory. Only RGB and configured prompts enter DINO; RGB-D recovery uses depth downstream.

Use `scripts/recovery/skill_pipeline/resident_mmdet_grounding_dino_worker.py` for native checkpoint inference. Its test pipeline removes annotation loading; it does not convert or load HF Grounding DINO weights.

Independent detection metrics and export limitations are recorded in [the training report](../../docs/results/dino_full_vocab_20261018.md). Detection precision is not an end-to-end recovery success rate. The pending full-episode evaluation is described in [the native recovery protocol](../../docs/results/rgbd_native_mmdet_20261018.md).
