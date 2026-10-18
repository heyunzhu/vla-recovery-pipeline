from pathlib import Path
import subprocess,json,os,hashlib,time
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');run=root/'logs/rgbd_box_geometry_20261016';code=run/'code'
env=dict(os.environ,PYTHONPATH=str(code),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MPLBACKEND='Agg')
py=str(root/'envs/rlinf-openpi/bin/python')
case=root/'logs/rgbd_framewise_expansion_20261016/03_goal_cheese_rack'
commands=[('tests',[py,'-m','unittest','experiments.robot.libero.skill_pipeline.tests.test_visual_observed_geometry','experiments.robot.libero.skill_pipeline.tests.test_visual_task_binding','experiments.robot.libero.skill_pipeline.tests.test_framewise_rgbd_tracker','experiments.robot.libero.skill_pipeline.tests.test_visual_placement_verification']),('audit',[py,str(code/'scripts/recovery/skill_pipeline/audit_observed_rgbd_geometry.py'),'--snapshot',str(case/'snapshots/recovery01/pre_solver_attempt01'),'--perception',str(run/'perception/recovery01/pre_solver_attempt01'),'--language','Put the cream cheese on the rack','--out',str(run/'audit')]),('comparison',[py,str(code/'scripts/recovery/skill_pipeline/compare_observed_geometry_offline.py'),'--geometry-dir',str(run/'audit'),'--oracle-problem',str(root/'logs/rgbd_ten_tasks_20261015/03_goal_cheese_rack/oracle/cutamp_debug/solve_1792034118342_67675.problem.json'),'--sensor',str(case/'snapshots/recovery01/pre_solver_attempt01/agentview')])]
(run/'validation_commands.json').write_text(json.dumps(dict(commands=commands,env={k:env[k] for k in ['PYTHONPATH','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MPLBACKEND']}),indent=2))
results={}
for name,argv in commands:
 with (run/(name+'.log')).open('wb') as log:
  p=subprocess.run(argv,env=env,cwd=code,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 results[name]=p.returncode
 (run/'validation_progress.json').write_text(json.dumps(results))
 if p.returncode:break
results['finished_unix']=time.time()
(run/'validation_finished.json').write_text(json.dumps(results,indent=2))
