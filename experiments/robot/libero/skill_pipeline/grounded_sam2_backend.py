"""Optional frozen Grounding DINO + SAM 2 backend for offline RGB frames.

This module imports model libraries only when instantiated. It receives an
RGBDObservation, but passes only its RGB array to the models. Prompts are
explicit configuration, never generated from simulator object names.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np

from .rgbd_observation import RGBDObservation
from .rgbd_scene import VisualDetection


def _normal_label(value: str) -> str:
    text = value.strip().lower().strip(". ")
    for article in ("a ", "an ", "the "):
        if text.startswith(article):
            return text[len(article) :]
    return text


def _to_numpy(value: object) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu()
    return np.asarray(value)


def _resolve_grounded_boxes(
    result: Mapping[str, object],
    prompts: Mapping[str, str],
    image_shape: tuple[int, int],
) -> tuple[list[list[float]], list[str], list[float]]:
    """Keep every allowed instance with a finite, nonempty image box."""

    names = {_normal_label(prompt): category for category, prompt in prompts.items()}
    labels = result.get("text_labels", result.get("labels"))
    if labels is None:
        raise ValueError("Grounding DINO result has no text labels")
    boxes = np.asarray(_to_numpy(result["boxes"]), dtype=np.float64)
    scores = np.asarray(_to_numpy(result["scores"]), dtype=np.float64)
    if boxes.ndim != 2 or boxes.shape[1] != 4 or scores.shape != (len(boxes),) or len(labels) != len(boxes):
        raise ValueError("Grounding DINO result has inconsistent boxes, scores, or labels")
    height, width = image_shape
    selected_boxes: list[list[float]] = []
    selected_categories: list[str] = []
    selected_scores: list[float] = []
    for box, score, label in zip(boxes, scores, labels):
        category = names.get(_normal_label(str(label)))
        if category is None:
            continue
        if not np.isfinite(box).all() or not np.isfinite(score):
            raise ValueError("Grounding DINO produced nonfinite box or score")
        x0, y0, x1, y1 = np.clip(box, [0, 0, 0, 0], [width, height, width, height]).tolist()
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        selected_boxes.append([x0, y0, x1, y1])
        selected_categories.append(category)
        selected_scores.append(float(score))
    return selected_boxes, selected_categories, selected_scores


class GroundedSam2Detector:
    def __init__(
        self,
        *,
        grounding_model: str,
        grounding_revision: str,
        sam2_model: str,
        sam2_revision: str,
        prompts: Mapping[str, str],
        box_threshold: float = 0.25,
        text_threshold: float = 0.25,
        device: str = "cpu",
        cache_dir: str | None = None,
    ) -> None:
        if not grounding_model or not grounding_revision or not sam2_model or not sam2_revision or not prompts:
            raise ValueError("pinned model references and at least one visual prompt are required")
        if any(not category.strip() or not prompt.strip() for category, prompt in prompts.items()):
            raise ValueError("visual categories and prompts cannot be blank")
        if len({_normal_label(prompt) for prompt in prompts.values()}) != len(prompts):
            raise ValueError("visual prompts must be unique after normalization")
        if not (0 < box_threshold <= 1 and 0 < text_threshold <= 1):
            raise ValueError("model thresholds must be in (0, 1]")

        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor, Sam2Model, Sam2Processor

        self._torch = torch
        self.prompts = dict(prompts)
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self.device = device
        self.grounding_processor = AutoProcessor.from_pretrained(
            grounding_model, revision=grounding_revision, cache_dir=cache_dir, local_files_only=True
        )
        self.grounding_model = AutoModelForZeroShotObjectDetection.from_pretrained(
            grounding_model, revision=grounding_revision, cache_dir=cache_dir,
            use_safetensors=True, local_files_only=True
        ).to(device).eval()
        self.sam2_processor = Sam2Processor.from_pretrained(
            sam2_model, revision=sam2_revision, cache_dir=cache_dir, local_files_only=True
        )
        self.sam2_model = Sam2Model.from_pretrained(
            sam2_model, revision=sam2_revision, cache_dir=cache_dir,
            use_safetensors=True, local_files_only=True
        ).to(device).eval()

    def __call__(self, frame: RGBDObservation) -> list[VisualDetection]:
        height, width = frame.rgb.shape[:2]
        image = np.ascontiguousarray(frame.rgb)
        inputs = self.grounding_processor(
            images=image,
            text=[list(self.prompts.values())],
            return_tensors="pt",
        ).to(self.device)
        with self._torch.no_grad():
            output = self.grounding_model(**inputs)
        result = self.grounding_processor.post_process_grounded_object_detection(
            output,
            inputs.input_ids,
            threshold=self.box_threshold,
            text_threshold=self.text_threshold,
            target_sizes=[(height, width)],
        )[0]
        self.last_grounding_boxes = [
            {"box_xyxy": box, "score": float(score), "text_label": str(label)}
            for box, score, label in zip(
                _to_numpy(result["boxes"]).tolist(),
                _to_numpy(result["scores"]).tolist(),
                result.get("text_labels", result.get("labels", [])),
            )
        ]
        boxes, categories, scores = _resolve_grounded_boxes(result, self.prompts, (height, width))
        if not boxes:
            return []
        sam_inputs = self.sam2_processor(images=image, input_boxes=[boxes], return_tensors="pt").to(self.device)
        with self._torch.no_grad():
            sam_output = self.sam2_model(**sam_inputs, multimask_output=False)
        masks = self.sam2_processor.post_process_masks(sam_output.pred_masks.cpu(), sam_inputs["original_sizes"])[0]
        masks = np.asarray(masks)
        if masks.shape != (len(boxes), 1, height, width):
            raise ValueError(f"SAM 2 returned unexpected mask shape {masks.shape}")
        return [
            VisualDetection(mask=np.asarray(masks[i, 0], dtype=bool), category=categories[i], raw_score=scores[i],
                            source="text_guided_segmentation")
            for i in range(len(boxes))
            if np.asarray(masks[i, 0]).any()
        ]
