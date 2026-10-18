from pathlib import Path
import subprocess,os,time
root=Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo")
run=root/"logs/oracle_anchor_rgbd_capture_20261009"
for _ in range(180):
 if (run/"exitcode.txt").exists(): break
 time.sleep(10)
else: raise RuntimeError("oracle capture did not finish")
if (run/"exitcode.txt").read_text().strip() != "0": raise RuntimeError("oracle capture failed")
env=dict(os.environ)
env["PYTHONPATH"]=str(root/"logs/rgbd_exact_box_20261008/pydeps")+":"+str(run/"visual_code")
env["HF_HUB_OFFLINE"]="1"
env["TRANSFORMERS_OFFLINE"]="1"
assets=root/"logs/rgbd_exact_box_20261008/models"
cmd=[str(root/"envs/tiptop-planning-py310/bin/python"),str(run/"visual_code/scripts/recovery/skill_pipeline/inspect_recovery_rgbd_capture.py"),str(run/"snapshots"),"--out-dir",str(run/"perception_joint"),"--grounding-model-dir",str(assets/"grounding-dino-tiny"),"--sam2-model-dir",str(assets/"sam2.1-hiera-tiny")]
with (run/"perception.log").open("wb") as f:
 rc=subprocess.call(cmd,stdout=f,stderr=subprocess.STDOUT,env=env)
(run/"perception_exitcode.txt").write_text(str(rc))
