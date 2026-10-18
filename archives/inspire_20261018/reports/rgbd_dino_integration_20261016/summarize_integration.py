import json,sys,csv
from pathlib import Path
from collections import Counter
r=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');o=r/'logs/rgbd_dino_integration_20261016';sys.path.insert(0,str(o/'code'))
from scripts.recovery.skill_pipeline.summarize_rgbd_task_batch import classify_artifacts,STAGES
statuses=json.loads((o/'recovery_status.json').read_text()) if (o/'recovery_status.json').exists() else []
old=json.loads((r/'logs/rgbd_ten_tasks_20261015/batch_results.json').read_text());meta={a['label']:a for a in old}
rows=[]
for run in sorted((o/'recovery').glob('*')):
 if not run.is_dir():continue
 case,res=run.name.rsplit('_',1);record=next((a for a in statuses if a['case']==case and a['resolution']==int(res)),{})
 def read(p):return json.loads(p.read_text()) if p.exists() else None
 replay=read(run/'replay_result.json');failure=read(run/'failure_result.json');bindings=sorted(run.glob('visual_nomination_step*/recovery01/pre_solver_attempt01/agentview/binding.json'));binding=read(bindings[-1]) if bindings else None
 solvers=sorted((run/'cutamp_debug').glob('*.result.json'));solver=read(solvers[-1]) if solvers else None
 logs='\n'.join(p.read_text(errors='replace') for p in [run/'driver.log',*run.glob('visual_nomination_step*.log')] if p.exists())
 stage,reason=classify_artifacts(replay=replay,failure=failure,binding=binding,logs=logs,solver=solver,visual_exit=record.get('returncode'))
 nom=bindings[-1].parent if bindings else None
 row={'case':case,'resolution':int(res),'stage':stage,'stage_name':STAGES[stage],'reason':reason,'binding':binding,'result':replay or failure,'exitcode':record.get('returncode'),'oracle_success':meta[case].get('oracle_run',{}).get('success'),'language':meta[case]['language'],'solver_feasible':solver.get('feasible') if solver else None,'solver_satisfying':solver.get('num_satisfying') if solver else None,'geometry_bottle':bool(nom and (nom/'bottle_model.json').exists()),'geometry_plate':bool(nom and (nom/'plate_model.json').exists()),'detection_count':len((read(nom/'visual_scene.json') or {}).get('objects',[])) if nom else None}
 rows.append(row)
ten=[a for a in rows if a['resolution']==640]
summary={'completed':sum(a['stage']!='pending' for a in ten),'selected':10,'success':sum(a['stage']=='success' for a in ten),'first_blockers':dict(Counter(a['stage'] for a in ten)),'rows':rows}
(o/'integration_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='rows'}));print([(a['case'],a['resolution'],a['stage'],a['reason']) for a in rows])
