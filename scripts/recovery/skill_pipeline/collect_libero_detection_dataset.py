#!/usr/bin/env python3
"""Collect paired native-resolution LIBERO RGB and visible-instance COCO boxes.

Simulator instance identities are used only to create offline training labels.
No policy, recovery controller, or online detector receives those identities.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import subprocess

CLASSES = ("wine bottle", "bowl", "plate", "basket", "rack", "cream cheese", "milk", "orange juice")


def category(name, class_name=""):
    def normal(s):
        return re.sub(r"[^a-z]", "", s.lower()).removesuffix("object")
    names = [normal(name), normal(class_name)]
    for value in names:
        if "winebottle" in value: return "wine bottle"
        if value.endswith("bowl"): return "bowl"
        if value.endswith("plate"): return "plate"
        if value.endswith("basket"): return "basket"
        if value in {"rack", "winerack", "woodenrack"}: return "rack"
        if "creamcheese" in value: return "cream cheese"
        if value in {"milk", "milkcarton"}: return "milk"
        if "orangejuice" in value: return "orange juice"
    return None


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def split_records(records, targets=(1000, 250, 250), seed=20261015):
    import numpy as np
    parents = {r["layout_group"]: r["layout_group"] for r in records}
    def find(k):
        while parents[k] != k:
            parents[k] = parents[parents[k]]; k = parents[k]
        return k
    seen = {}
    for r in records:
        key = r["pixel_sha256"]
        if key in seen:
            a, b = find(r["layout_group"]), find(seen[key]); parents[a] = b
        else:
            seen[key] = r["layout_group"]
    groups = defaultdict(list)
    for r in records: groups[find(r["layout_group"])].append(r)
    rng = np.random.default_rng(seed)
    keys = list(sorted(groups)); rng.shuffle(keys)
    pools = [[], [], []]
    for key in sorted(keys, key=lambda k: -len(groups[k])):
        i = max(range(3), key=lambda j: (targets[j] - len(pools[j])) / targets[j])
        pools[i].extend(groups[key])
    selected = {}
    for name, pool, target in zip(("train", "val", "test"), pools, targets):
        if len(pool) < target:
            raise ValueError(f"insufficient {name} after leakage-safe grouping: {len(pool)} < {target}; collect more episodes")
        order = rng.permutation(len(pool))[:target]
        selected[name] = [pool[int(i)] for i in order]
    group_sets = [{find(r["layout_group"]) for r in selected[k]} for k in ("train", "val", "test")]
    assert all(not group_sets[i] & group_sets[j] for i in range(3) for j in range(i))
    return selected, {"group_count": len(groups), "candidate_pool_counts": [len(p) for p in pools],
                      "selected_counts": {k: len(v) for k, v in selected.items()},
                      "layout_groups_disjoint": True, "identical_rgb_groups_merged": True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--libero", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--gpu", type=int, default=1)
    p.add_argument("--episodes-per-task", type=int, default=6)
    p.add_argument("--samples-per-episode", type=int, default=10)
    p.add_argument("--train-count", type=int, default=1000)
    p.add_argument("--val-count", type=int, default=250)
    p.add_argument("--test-count", type=int, default=250)
    p.add_argument("--seed", type=int, default=20261015)
    p.add_argument("--suites", nargs="+", default=["libero_object", "libero_goal", "libero_spatial"])
    p.add_argument("--tasks-per-suite", type=int, default=0)
    p.add_argument("--collect-only", action="store_true")
    args = p.parse_args()
    if args.output.exists() and any(args.output.iterdir()): raise ValueError("output must be empty")
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.libero))
    import numpy as np
    import torch
    from PIL import Image, ImageDraw
    from libero.libero import benchmark, get_libero_path
    from libero.libero.envs import OffScreenRenderEnv
    from robosuite.utils.binding_utils import MjRenderContextOffscreen

    write(args.output / "manifest.json", {"args": vars(args) | {"libero": str(args.libero), "output": str(args.output)},
          "classes": CLASSES, "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "annotation_policy": "Every visible selected-class instance; tight visible-surface bbox, no amodal completion.",
          "camera_policy": "8 agentview + 2 wrist samples per 10-step episode sample sequence",
          "segmentation_antialias_samples": 0, "rgb_antialias_samples": "original model default unchanged",
          "split_policy": "group initial physical layout, merge groups containing identical RGB, then select fixed quotas",
          "libero_commit": subprocess.check_output(["git", "-C", str(args.libero), "rev-parse", "HEAD"], text=True).strip(),
          "libero_dirty_status": subprocess.check_output(["git", "-C", str(args.libero), "status", "--short"], text=True)})
    records = []; object_audits = []; task_sources = []; episode_index = 0
    logs = (args.output / "records.jsonl").open("w", encoding="utf-8")
    try:
        for suite_name in args.suites:
            suite = benchmark.get_benchmark_dict()[suite_name]()
            for task_id in range(min(suite.n_tasks, args.tasks_per_suite or suite.n_tasks)):
                task = suite.get_task(task_id)
                bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
                init_path = Path(get_libero_path("init_states")) / task.problem_folder / task.init_states_file
                init_states = torch.load(init_path, map_location="cpu", weights_only=False)
                task_sources.append({"suite": suite_name, "task_id": task_id, "language": task.language,
                    "bddl": str(bddl), "bddl_sha256": hashlib.sha256(bddl.read_bytes()).hexdigest(),
                    "init_states": str(init_path), "init_sha256": hashlib.sha256(init_path.read_bytes()).hexdigest()})
                write(args.output / "task_sources.json", task_sources)
                env = OffScreenRenderEnv(bddl_file_name=str(bddl), use_camera_obs=False,
                                         camera_heights=640, camera_widths=640, render_gpu_device_id=args.gpu)
                try:
                    for init_id in np.linspace(0, len(init_states)-1, args.episodes_per_task, dtype=int):
                        episode = f"{suite_name}_t{task_id:02d}_i{init_id:02d}"
                        seed = args.seed + episode_index * 101
                        rng = np.random.default_rng(seed)
                        env.seed(seed); env.reset(); env.set_init_state(init_states[int(init_id)])
                        sim = env.env.sim; model = sim.model
                        # Color-ID segmentation must not blend edge colors into
                        # unrelated geom IDs. Preserve normal RGB antialiasing
                        # in its own context and disable it only for label render.
                        rgb_ctx = sim._render_context_offscreen
                        rgb_ctx.gl_ctx.make_current()
                        rgb_ctx.update_offscreen_size(640, 640)
                        original_samples = int(model.vis.quality.offsamples)
                        model.vis.quality.offsamples = 0
                        try:
                            seg_ctx = MjRenderContextOffscreen(sim, device_id=args.gpu, max_width=640, max_height=640)
                        finally:
                            model.vis.quality.offsamples = original_samples
                        seg_ctx.vopt.geomgroup[:] = rgb_ctx.vopt.geomgroup
                        seg_ctx.vopt.sitegroup[:] = rgb_ctx.vopt.sitegroup
                        seg_ctx.vopt.flags[:] = rgb_ctx.vopt.flags
                        assert seg_ctx.con.offSamples == 0
                        sim._render_context_offscreen = rgb_ctx
                        objects = {**env.env.fixtures_dict, **env.env.objects_dict}
                        object_rows = []
                        for name, obj in objects.items():
                            root_id = model.body_name2id(obj.root_body)
                            object_rows.append({"name": name, "class_name": type(obj).__name__,
                                                "category": category(name, type(obj).__name__), "body_id": int(root_id)})
                        initial = [{"name": o["name"], "class": o["class_name"],
                                    "position": np.round(sim.data.body_xpos[o["body_id"]], 4).tolist(),
                                    "quaternion": np.round(sim.data.body_xquat[o["body_id"]], 4).tolist()}
                                   for o in sorted(object_rows, key=lambda x: x["name"])]
                        layout = hashlib.sha256(json.dumps(initial, sort_keys=True).encode()).hexdigest()
                        selected_objects = [o for o in object_rows if o["category"] is not None]
                        category_by_name = {o["name"]: o["category"] for o in selected_objects}
                        goal_roles = []
                        for atom in env.env.parsed_problem.get("goal_state", []):
                            if (len(atom) >= 3 and str(atom[0]).lower() in {"on", "in", "inside"}
                                    and atom[1] in category_by_name and atom[2] in category_by_name):
                                goal_roles.append({"target_instance": atom[1], "goal_instance": atom[2],
                                    "target_category": category_by_name[atom[1]], "goal_category": category_by_name[atom[2]]})
                        object_audits.append({"episode": episode, "objects": object_rows, "layout_group": layout})
                        roots = {o["body_id"]: i+1 for i, o in enumerate(selected_objects)}
                        lut = np.zeros(model.ngeom, dtype=np.uint16); robot_lut = np.zeros(model.ngeom, dtype=bool)
                        for geom_id in range(model.ngeom):
                            body = int(model.geom_bodyid[geom_id])
                            while body:
                                if body in roots:
                                    lut[geom_id] = roots[body]; break
                                body = int(model.body_parentid[body])
                            name = model.geom_id2name(geom_id) or ""
                            robot_lut[geom_id] = name.startswith(("robot0_", "gripper0_", "mount0_"))
                        # Sparse sampled RGB only: stepping never renders camera observations.
                        for sample in range(args.samples_per_episode):
                            action = rng.uniform(-.45, .45, size=7)
                            action[2] *= .5; action[3:6] *= .7; action[6] = rng.choice([-1., 1.])
                            for _ in range(10): env.step(action)
                            camera = "robot0_eye_in_hand" if sample % 5 == 4 else "agentview"
                            image_id = episode_index * args.samples_per_episode + sample + 1
                            stem = f"{episode}_s{sample:02d}"
                            per_res = {}
                            for resolution in (640, 256):
                                camera_id = model.camera_name2id(camera)
                                rgb_ctx.gl_ctx.make_current()
                                rgb_ctx.render(resolution, resolution, camera_id=camera_id, segmentation=False)
                                rgb = np.ascontiguousarray(rgb_ctx.read_pixels(resolution, resolution)[::-1])
                                seg_ctx.gl_ctx.make_current()
                                seg_ctx.render(resolution, resolution, camera_id=camera_id, segmentation=True)
                                seg = seg_ctx.read_pixels(resolution, resolution, segmentation=True)[::-1]
                                ids = seg[..., 1]; valid = (seg[..., 0] == 5) & (ids >= 0) & (ids < model.ngeom)
                                instance = np.zeros(ids.shape, dtype=np.uint16)
                                instance[valid] = lut[ids[valid]]
                                robot = np.zeros(ids.shape, dtype=bool); robot[valid] = robot_lut[ids[valid]]
                                annotations = []
                                for instance_id, obj in enumerate(selected_objects, 1):
                                    ys, xs = np.nonzero(instance == instance_id)
                                    if not len(xs): continue
                                    x, y = int(xs.min()), int(ys.min()); w, h = int(xs.max())-x+1, int(ys.max())-y+1
                                    annotations.append({"category_id": CLASSES.index(obj["category"])+1,
                                        "bbox": [x, y, w, h], "area": w*h, "iscrowd": 0,
                                        "visible_pixels": len(xs), "instance_name": obj["name"]})
                                directory = args.output / f"images{resolution}"; directory.mkdir(exist_ok=True)
                                relative = f"images{resolution}/{stem}.png"
                                Image.fromarray(rgb).save(args.output / relative, compress_level=1)
                                mask_dir = args.output / f"instance_masks{resolution}"; mask_dir.mkdir(exist_ok=True)
                                instance[robot] = 65535
                                Image.fromarray(instance).save(mask_dir / f"{stem}.png")
                                per_res[str(resolution)] = {"file_name": relative, "annotations": annotations}
                                if resolution == 640:
                                    pixel_sha = hashlib.sha256(rgb.tobytes()).hexdigest()
                                    if sample in (0, 4) and init_id == 0:
                                        overlay = Image.fromarray(rgb); draw = ImageDraw.Draw(overlay)
                                        for a in annotations:
                                            x,y,w,h = a["bbox"];draw.rectangle((x,y,x+w,y+h),outline="lime",width=2)
                                            draw.text((x,max(0,y-12)),CLASSES[a["category_id"]-1],fill="lime",stroke_width=1,stroke_fill="black")
                                        qa = args.output / "qa";qa.mkdir(exist_ok=True);overlay.save(qa/f"{stem}.png")
                            states = args.output / "states"; states.mkdir(exist_ok=True)
                            np.save(states / f"{stem}.npy", sim.get_state().flatten())
                            row = {"id": image_id, "episode": episode, "suite": suite_name, "task_id": task_id,
                                   "init_id": int(init_id), "seed": seed, "step": (sample+1)*10,
                                   "camera": camera, "language": task.language, "layout_group": layout,
                                   "goal_role_pairs": goal_roles,
                                   "pixel_sha256": pixel_sha, "resolutions": per_res}
                            records.append(row);logs.write(json.dumps(row)+"\n");logs.flush()
                        del seg_ctx
                        rgb_ctx.gl_ctx.make_current()
                        episode_index += 1
                        print(json.dumps({"episode": episode,"candidate_frames":len(records)}),flush=True)
                finally:
                    env.close()
    finally:
        logs.close()
    write(args.output / "object_identity_audit.json", object_audits)
    if args.collect_only:
        write(args.output / "collection_complete.json", {"candidate_frames": len(records)})
        return
    selected, split_audit = split_records(records, (args.train_count,args.val_count,args.test_count),args.seed)
    categories = [{"id": i+1, "name": c} for i,c in enumerate(CLASSES)]
    counts = {}
    for split, subset in selected.items():
        for resolution in (640,256):
            images, anns = [], []
            for row in sorted(subset,key=lambda x:x["id"]):
                item = row["resolutions"][str(resolution)]
                images.append({"id":row["id"],"file_name":item["file_name"],"width":resolution,"height":resolution,
                    "episode":row["episode"],"layout_group":row["layout_group"],"camera":row["camera"],"task_language":row["language"],
                    "goal_role_pairs": row["goal_role_pairs"]})
                for a in item["annotations"]:anns.append({**a,"id":len(anns)+1,"image_id":row["id"]})
            write(args.output/f"annotations/{split}{resolution}.json",{"images":images,"annotations":anns,"categories":categories})
            counts[f"{split}{resolution}"] = dict(Counter(CLASSES[a["category_id"]-1] for a in anns))
            if resolution==640 and set(counts[f"{split}{resolution}"]) != set(CLASSES):
                raise ValueError(f"class missing from {split}: {counts[f'{split}{resolution}']}")
    write(args.output/"splits.json",{k:[r["id"] for r in v] for k,v in selected.items()})
    write(args.output/"dataset_audit.json",{**split_audit,"candidate_frames":len(records),"class_counts":counts})
    write(args.output/"completed.json",{"selected_frames":sum(len(v) for v in selected.values()),"candidate_frames":len(records)})


if __name__ == "__main__": main()
