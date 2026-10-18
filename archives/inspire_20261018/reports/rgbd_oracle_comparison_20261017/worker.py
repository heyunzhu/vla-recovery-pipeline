import argparse,json
from pathlib import Path
from types import SimpleNamespace
import importlib.util

p=argparse.ArgumentParser();p.add_argument('--problem',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--hard-rack',action='store_true');a=p.parse_args()
from experiments.robot.libero.tiptop_repro import real_cutamp_backend as backend
if a.hard_rack:
 original=backend._exclude_target_support_surface_collision
 def exclude(obj,names):
  if obj.name=='wine_rack_1_main':return False
  return original(obj,names)
 backend._exclude_target_support_surface_collision=exclude
source=Path(__file__).with_name('diagnose_rgbd_bowl_constraints.py')
spec=importlib.util.spec_from_file_location('constraint_capture',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.worker(SimpleNamespace(problem=a.problem,out_dir=a.out_dir,variant='baseline',seed=0,wall_names=[],capture=True))
