from pathlib import Path
import json
import sys
from PIL import Image, ImageDraw, ImageFont

root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs')
out=root/'rgbd_dino_integration_20261016'
sys.path.insert(0,str(out/'code'))
from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
cases=['03_goal_cheese_rack','04_swap_bowl_plate','05_swap_cheese_bowl','08_object_milk_basket']
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
board=Image.new('RGB',(800,1776),'#171c23')
draw=ImageDraw.Draw(board)
for row,case in enumerate(cases):
    for col,kind in enumerate(('before','after')):
        base=root/'rgbd_ten_tasks_20261015'/case/'visual' if kind=='before' else out/'recovery'/f'{case}_640'
        n=next(base.glob('visual_nomination_step*/recovery01/pre_solver_attempt01/agentview'))
        config=json.loads((n.parents[2]/'run_config.json').read_text())
        prompts=prompts_from_task_language(config['language'])
        rgb=Image.open(n/'rgb.png').convert('RGB')
        panel=rgb.resize((384,384));d=ImageDraw.Draw(panel)
        detections=json.loads((n/'detections.json').read_text())['detections']
        scene=json.loads((n/'visual_scene.json').read_text())
        found=[]
        for obj in scene['objects']:
            category=obj['category']
            if category not in prompts or not obj.get('pixel_bbox_xyxy'):continue
            coords=[v*384/rgb.width for v in obj['pixel_bbox_xyxy']]
            score=detections[obj['detection_index']]['raw_score']
            color=['#ffcc55','#58e6af'][list(prompts).index(category)%2]
            d.rectangle(coords,outline=color,width=2)
            d.text((coords[0],max(0,coords[1]-17)),category+' '+str(round(score,2)),font=small,fill=color,stroke_width=1,stroke_fill='black')
            found.append(category)
        x,y=col*400+8,row*444+40
        board.paste(panel,(x,y))
        draw.text((x,row*444+10),case+' '+('original 256' if col==0 else 'finetuned 640'),font=font,fill='white')
        draw.text((x,row*444+426),'Accepted: '+', '.join(dict.fromkeys(found)),font=small,fill='#c7d2df')
board.save(out/'recovery_detection_comparison.png')
