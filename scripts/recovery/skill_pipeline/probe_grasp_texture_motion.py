"""Offline assisted texture tracking; motion evidence is not a holding verdict."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

from probe_static_wrist_gripper import pose, read_stl, raster_depth


def match_patch(template, image, center, radius=8, search=28):
    """Return normalized correlation, separated runner-up margin and pixel center."""
    x, y = center
    lo_x, hi_x = max(radius, x-search), min(image.shape[1]-radius-1, x+search)
    lo_y, hi_y = max(radius, y-search), min(image.shape[0]-radius-1, y+search)
    crop = image[lo_y-radius:hi_y+radius+1, lo_x-radius:hi_x+radius+1]
    windows = np.lib.stride_tricks.sliding_window_view(crop, template.shape)
    t = template-template.mean()
    centered = windows-windows.mean(axis=(-2, -1), keepdims=True)
    denom = np.sqrt(np.sum(centered**2, axis=(-2, -1))*np.sum(t*t))
    scores = np.divide(np.sum(centered*t, axis=(-2, -1)), denom,
                       out=np.full(denom.shape, -1.), where=denom>1e-8)
    yy, xx = np.unravel_index(np.argmax(scores), scores.shape)
    peak = float(scores[yy, xx])
    competitors = scores.copy()
    competitors[max(0,yy-4):yy+5, max(0,xx-4):xx+5] = -1
    return (int(xx+lo_x), int(yy+lo_y)), peak, peak-float(competitors.max())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--model-dir', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--labels', nargs='+', default=['after_close','lift5mm','lift20mm','lift40mm','after_hold'])
    args = p.parse_args()
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation, unproject_world
    from experiments.robot.libero.skill_pipeline.perception_artifact import rgb_sha256
    from experiments.robot.libero.skill_pipeline.visual_mask_depth_diagnostic import validate_synchronized_views
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = json.loads((args.model_dir/'manifest.json').read_text())
    for name, expected in manifest['source_sha256'].items():
        if sha(args.model_dir/name) != expected: raise ValueError('static model changed: '+name)
    arm = ET.parse(args.model_dir/'models/assets/robots/panda/robot.xml')
    grip = ET.parse(args.model_dir/'models/assets/grippers/panda_gripper.xml')
    hc = pose(arm.find('.//body[@name="right_hand"]/camera[@name="eye_in_hand"]')) @ np.diag([1,-1,-1,1])
    meshes = {e.get('name'):read_stl(args.model_dir/'models/assets/grippers'/e.get('file')) for e in grip.findall('./asset/mesh')}
    args.out_dir.mkdir(exist_ok=False)
    labels = args.labels
    if len(labels)<2 or len(set(labels))!=len(labels) or labels[0]!='after_close':
        raise ValueError('unique labels starting with after_close required')
    frames, gray, coordinates, robots, hands = {}, {}, {}, {}, {}
    inputs = {}
    for label in labels:
        f = load_observation(args.dataset/label/'robot0_eye_in_hand')
        a = load_observation(args.dataset/label/'agentview')
        validate_synchronized_views(f, a)
        frames[label] = f
        if frames[labels[0]].episode_id != f.episode_id:
            raise ValueError('cross-episode motion inputs')
        if len(frames)>1 and f.env_step<=frames[labels[len(frames)-2]].env_step:
            raise ValueError('motion frames must advance in time')
        gray[label] = np.asarray(Image.fromarray(f.rgb).convert('L'), dtype=float)/255
        coords = np.full((*f.depth_m.shape,3), np.nan)
        coords[f.depth_valid] = unproject_world(f)
        coordinates[label] = coords
        hands[label] = f.T_world_camera @ np.linalg.inv(hc)
        qmap = dict(zip(('finger_joint1','finger_joint2'), f.robot_state['robot0_gripper_qpos']))
        triangles = []
        def visit(body, parent):
            t = parent @ pose(body)
            for joint in body.findall('./joint'):
                if joint.get('type') != 'slide' or joint.get('name') not in qmap: raise ValueError('unsupported joint')
                jt = np.eye(4); jt[:3,3] = np.array([float(v) for v in joint.get('axis').split()])*qmap[joint.get('name')]
                t = t @ jt
            for geom in body.findall('./geom'):
                if geom.get('group') == '1' and geom.get('type') == 'mesh':
                    gt = np.linalg.inv(hc) @ t @ pose(geom)
                    triangles.append(meshes[geom.get('mesh')] @ gt[:3,:3].T + gt[:3,3])
            for child in body.findall('./body'): visit(child, t)
        visit(grip.find('./worldbody/body'), np.eye(4))
        d, skipped = raster_depth(np.concatenate(triangles), f.K, f.depth_m.shape)
        robots[label] = np.isfinite(d) & f.depth_valid & (np.abs(f.depth_m-d)<=.005)
        for camera in ('agentview','robot0_eye_in_hand'):
            for name in ('metadata.json','rgbd.npz'):
                path = args.dataset/label/camera/name; inputs[str(path)] = sha(path)
    source = labels[0]; radius = 8
    # These regions are assistant visual drafts in this episode, not semantic ground truth.
    regions = dict(front_bowl_draft=[25,295,190,380], plate_control_draft=[20,150,235,215])
    report_rows = []
    for region, (x0,y0,x1,y1) in regions.items():
        anchors = []
        for y in range(y0+radius,y1-radius,12):
            for x in range(x0+radius,x1-radius,12):
                patch = gray[source][y-radius:y+radius+1,x-radius:x+radius+1]
                if patch.std() >= .025 and frames[source].depth_valid[y,x] and not robots[source][y,x]:
                    anchors.append((float(patch.std()),x,y))
        chosen = []
        for _,x,y in sorted(anchors,reverse=True):
            if all(np.hypot(x-px,y-py)>=24 for px,py in chosen): chosen.append((x,y))
            if len(chosen)>=20: break
        for label in labels[1:]:
            tracks = []
            for x,y in chosen:
                template = gray[source][y-radius:y+radius+1,x-radius:x+radius+1]
                (tx,ty),score,margin = match_patch(template,gray[label],(x,y),radius)
                target_patch = gray[label][ty-radius:ty+radius+1,tx-radius:tx+radius+1]
                (bx,by),back_score,_ = match_patch(target_patch,gray[source],(tx,ty),radius)
                fb = float(np.hypot(bx-x,by-y))
                valid = frames[label].depth_valid[ty,tx] and not robots[label][ty,tx]
                accepted = bool(score>=.90 and margin>=.015 and back_score>=.90 and fb<=2 and valid)
                row = dict(source_xy=[x,y],target_xy=[tx,ty],ncc=score,peak_margin=margin,reverse_ncc=back_score,forward_backward_error_px=fb,accepted=accepted)
                if accepted:
                    s = coordinates[source][y,x]; t = coordinates[label][ty,tx]
                    eef_delta = np.asarray(frames[label].robot_state['robot0_eef_pos'])-frames[source].robot_state['robot0_eef_pos']
                    local_s = (np.linalg.inv(hands[source]) @ np.r_[s,1])[:3]
                    local_t = (np.linalg.inv(hands[label]) @ np.r_[t,1])[:3]
                    row.update(source_world_m=s.tolist(),target_world_m=t.tolist(),world_delta_m=(t-s).tolist(),eef_delta_m=eef_delta.tolist(),world_delta_minus_eef_m=(t-s-eef_delta).tolist(),hand_relative_displacement_m=float(np.linalg.norm(local_t-local_s)))
                tracks.append(row)
            accepted = [r for r in tracks if r['accepted']]
            report_rows.append(dict(region=region,label=label,env_step=frames[label].env_step,anchor_count=len(chosen),accepted_count=len(accepted),tracks=tracks,
                median_world_delta_m=np.median([r['world_delta_m'] for r in accepted],axis=0).tolist() if accepted else None,
                median_hand_relative_displacement_m=float(np.median([r['hand_relative_displacement_m'] for r in accepted])) if accepted else None))
            im = Image.fromarray(frames[label].rgb); draw = ImageDraw.Draw(im)
            for row in tracks:
                tx,ty=row['target_xy']; color='lime' if row['accepted'] else 'red'
                draw.ellipse((tx-3,ty-3,tx+3,ty+3),outline=color,width=2)
            im.save(args.out_dir/(region+'_'+label+'.png'))
    report = dict(scope='offline_assisted_wrist_texture_motion',episode_id=frames[source].episode_id,
        selection_source='assistant_explicit_visual_roi',human_reviewed=False,blind_evaluation=False,
        source_label=source,source_rgb_sha256=rgb_sha256(frames[source]),regions_xyxy=regions,
        settings=dict(patch_radius_px=radius,search_radius_px=28,ncc_min=.90,separated_peak_margin_min=.015,forward_backward_max_px=2,robot_depth_tolerance_m=.005),
        results=report_rows,input_sha256=inputs,source_sha256={str(Path(__file__)):sha(Path(__file__))},
        static_model_manifest_sha256=sha(args.model_dir/'manifest.json'),environment_actions=0,
        identity_verified=False,holding_verified=False,task_success_verified=False,
        limitations=['texture correspondences are hypotheses','ROI labels are assistant drafts','point tracks do not verify contact or sustained grasp','only visual gripper meshes projected; no full arm segmentation'])
    (args.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps([{k:r[k] for k in ('region','label','anchor_count','accepted_count','median_world_delta_m','median_hand_relative_displacement_m')} for r in report_rows],indent=2))


if __name__ == '__main__': main()
