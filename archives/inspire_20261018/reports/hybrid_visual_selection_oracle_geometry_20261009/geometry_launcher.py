from pathlib import Path
import os,subprocess,time
root=Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo")
run=root/"logs/hybrid_visual_selection_oracle_geometry_20261009"
for _ in range(180):
 if (run/"exitcode.txt").exists():break
 time.sleep(10)
else:raise RuntimeError("hybrid did not finish")
if (run/"exitcode.txt").read_text().strip()!="0":raise RuntimeError("hybrid failed; do not advance geometry")
code=root/"logs/oracle_anchor_rgbd_capture_20261009/visual_code"
env=dict(os.environ)
env["PYTHONPATH"]=":".join(map(str,[code,root/"logs/rgbd_exact_box_20261008/pydeps",root/"third_party/cuTAMP",root/"third_party/curobo"]))
env.update(CUDA_VISIBLE_DEVICES="0",MUJOCO_GL="egl",PYOPENGL_PLATFORM="egl",OMP_NUM_THREADS="2")
source=run/"snapshots/recovery01/pre_solver_attempt01"
cmd=[str(root/"envs/tiptop-planning-py310/bin/python"),str(code/"scripts/recovery/skill_pipeline/run_exact_box_task.py"),"--observation-dir",str(source/"agentview"),"--detector-dir",str(run/"visual_nomination_step41/recovery01/pre_solver_attempt01/agentview"),"--summary-json",str(source/"capture_audit.json"),"--out-dir",str(run/"visual_geometry_diagnostic")]
with (run/"visual_geometry_diagnostic.log").open("wb") as f:
 rc=subprocess.call(cmd,env=env,stdout=f,stderr=subprocess.STDOUT)
(run/"geometry_exitcode.txt").write_text(str(rc))
