#!/usr/bin/env python3
"""Render cached visual masks over their exact RGB frame."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


PALETTE = np.asarray(
    [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0], [255, 0, 255], [0, 255, 255]],
    dtype=np.uint8,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("detections_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from scripts.recovery.skill_pipeline.render_rgbd_diagnostic import _write_rgb_png

    frame = load_observation(args.snapshot)
    detector_id, detections = load_detections(frame, args.detections_dir)
    overlay = frame.rgb.copy()
    legend = []
    for index, detection in enumerate(detections):
        color = PALETTE[index % len(PALETTE)]
        mask = detection.mask
        overlay[mask] = (0.5 * overlay[mask] + 0.5 * color).astype(np.uint8)
        legend.append(
            {
                "mask_index": index,
                "category": detection.category,
                "raw_score": detection.raw_score,
                "source": detection.source,
                "color_rgb": color.tolist(),
                "pixel_count": int(mask.sum()),
            }
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _write_rgb_png(args.out, overlay)
    args.out.with_suffix(".json").write_text(
        json.dumps({"detector_id": detector_id, "masks": legend}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"detector_id": detector_id, "mask_count": len(detections)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
