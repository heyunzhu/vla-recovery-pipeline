"""Offline detection, segmentation and binding audit of captured recovery frames."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_root", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--grounding-model-dir", type=Path, required=True)
    parser.add_argument("--sam2-model-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.25)
    parser.add_argument("--camera", choices=("both", "agentview", "robot0_eye_in_hand"), default="both")
    parser.add_argument("--phase", help="Only inspect this capture phase")
    parser.add_argument("--fit-target-bottle", action="store_true")
    parser.add_argument("--fit-goal-plate", action="store_true")
    parser.add_argument("--obstacle-robot-model-dir", type=Path)
    parser.add_argument("--distractor-prompts-json", type=Path,
                        help="Explicit generic scene categories; no simulator metadata")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    import numpy as np
    from PIL import Image, ImageDraw
    from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector
    from experiments.robot.libero.skill_pipeline.perception_artifact import save_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
    from experiments.robot.libero.skill_pipeline.visual_task_binding import bind_visual_pick_place
    from run_grounded_sam2_snapshot import (
        _verify_model_weights, GROUNDING_SHA256, SAM2_SHA256,
        GROUNDING_REVISION, SAM2_REVISION,
    )

    audits = sorted(args.capture_root.glob("recovery*/**/capture_audit.json"))
    if not audits:
        raise ValueError("no recovery captures")
    languages = {json.loads(p.read_text())["language"] for p in audits}
    if len(languages) != 1:
        raise ValueError("this diagnostic requires one task language")
    language = languages.pop()
    prompts = prompts_from_task_language(language)
    if args.distractor_prompts_json:
        distractors = json.loads(args.distractor_prompts_json.read_text())
        if not isinstance(distractors, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in distractors.items()
        ):
            raise ValueError("distractor prompts must map categories to descriptions")
        if prompts.keys() & distractors.keys():
            raise ValueError("distractors cannot override task categories")
        prompts.update(distractors)
    grounding = _verify_model_weights(args.grounding_model_dir, GROUNDING_SHA256)
    sam = _verify_model_weights(args.sam2_model_dir, SAM2_SHA256)
    detector = GroundedSam2Detector(
        grounding_model=str(grounding), grounding_revision=GROUNDING_REVISION,
        sam2_model=str(sam), sam2_revision=SAM2_REVISION, prompts=prompts,
        device=args.device, grounding_mode="joint", box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
    )
    config = dict(language=language, prompts=prompts, grounding_mode="joint",
                  box_threshold=args.box_threshold, text_threshold=args.text_threshold,
                  grounding_sha256=GROUNDING_SHA256, sam2_sha256=SAM2_SHA256,
                  ground_truth_used_for_detection=False, environment_actions=0)
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir / "run_config.json").write_text(json.dumps(config, indent=2))
    results = []
    for audit_path in audits:
        audit = json.loads(audit_path.read_text())
        if args.phase and audit["phase"] != args.phase:
            continue
        cameras = ("agentview", "robot0_eye_in_hand") if args.camera == "both" else (args.camera,)
        for camera in cameras:
            source = audit_path.parent / camera
            frame = load_observation(source)
            out = args.out_dir / source.relative_to(args.capture_root)
            detections = detector(frame)
            save_detections(frame, detections, out, detector_id="anchor-grounded-sam2-joint")
            boxes = detector.last_grounding_boxes
            (out / "grounding_boxes.json").write_text(json.dumps(boxes, indent=2))
            provider = RGBDSceneProvider(lambda _: detections,
                detector_id="anchor-grounded-sam2-joint", camera_id=camera)
            scene = provider.get_scene(frame)
            binding = bind_visual_pick_place(language, scene)
            if args.fit_target_bottle:
                from experiments.robot.libero.skill_pipeline.visual_bottle_geometry import fit_upright_bottle
                from experiments.robot.libero.skill_pipeline.rgbd_observation import unproject_world
                target = next(obj for obj in scene.objects if obj.id == binding.target_id)
                if target.category != "bottle":
                    raise ValueError("bottle fitting requires a visually nominated bottle")
                world = np.full((*frame.depth_m.shape, 3), np.nan)
                world[frame.depth_valid] = unproject_world(frame)
                model, retained = fit_upright_bottle(world, detections[target.detection_index].mask)
                model.update(snapshot_id=scene.snapshot_id, visual_id=target.id)
                (out / "bottle_model.json").write_text(json.dumps(model, indent=2))
                np.savez_compressed(out / "bottle_points.npz", raw=world[detections[target.detection_index].mask],
                                    retained=world[retained], retained_mask=retained)
            if args.fit_goal_plate:
                from experiments.robot.libero.skill_pipeline.visual_plate_geometry import fit_plate_support
                from experiments.robot.libero.skill_pipeline.rgbd_observation import unproject_world
                goal = next(obj for obj in scene.objects if obj.id == binding.goal_id)
                if goal.category != "plate":
                    raise ValueError("plate fitting requires a visually nominated plate")
                world = np.full((*frame.depth_m.shape, 3), np.nan)
                world[frame.depth_valid] = unproject_world(frame)
                model = fit_plate_support(world, detections[goal.detection_index].mask)
                model.update(snapshot_id=scene.snapshot_id, visual_id=goal.id)
                (out / "plate_model.json").write_text(json.dumps(model, indent=2))
            if args.obstacle_robot_model_dir:
                from experiments.robot.libero.skill_pipeline.visual_arm_pixels import project_static_arm_gripper
                from experiments.robot.libero.skill_pipeline.visual_anchor_obstacles import observed_anchor_obstacles
                selected = [obj for obj in scene.objects if obj.id in (binding.target_id, binding.goal_id)]
                excluded = np.logical_or.reduce([detections[obj.detection_index].mask for obj in selected])
                robot = project_static_arm_gripper(frame, args.obstacle_robot_model_dir, depth_tolerance_m=.005)
                from experiments.robot.libero.skill_pipeline.robot_surface_ownership import augment_robot_surface_ownership
                robot = augment_robot_surface_ownership(frame, robot, args.obstacle_robot_model_dir)
                target = next(obj for obj in selected if obj.id == binding.target_id)
                fitted_bottle = json.loads((out/'bottle_model.json').read_text()) if args.fit_target_bottle else None
                obstacles = observed_anchor_obstacles(frame, excluded, robot,
                    bottle_model=fitted_bottle, bottle_mask=detections[target.detection_index].mask)
                (out / 'obstacles.json').write_text(json.dumps(obstacles, indent=2))
            for filename, data in (("visual_scene.json", asdict(scene)), ("binding.json", asdict(binding))):
                (out / filename).write_text(json.dumps(data, indent=2))
            Image.fromarray(frame.rgb).save(out / "rgb.png")
            overlay = frame.rgb.astype(float)
            colors = ((255, 60, 60), (40, 220, 80), (50, 140, 255), (240, 200, 30))
            for i, detection in enumerate(detections):
                overlay[detection.mask] = 0.55 * overlay[detection.mask] + 0.45 * np.array(colors[i % len(colors)])
            annotated = Image.fromarray(overlay.astype(np.uint8)).resize((768, 768))
            draw = ImageDraw.Draw(annotated)
            for i, obj in enumerate(scene.objects):
                if obj.pixel_bbox_xyxy:
                    box = [int(v * 3) for v in obj.pixel_bbox_xyxy]
                    draw.rectangle(box, outline=colors[i % len(colors)], width=2)
                    draw.text((box[0], max(0, box[1] - 13)), f"{i}: {obj.category}", fill="white", stroke_fill="black", stroke_width=1)
            annotated.save(out / "overlay.png")
            results.append(dict(phase=audit["phase"], camera=camera, control_steps=frame.env_step,
                                detection_count=len(detections), binding=asdict(binding)))
            print(json.dumps(results[-1]), flush=True)
    (args.out_dir / "summary.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
