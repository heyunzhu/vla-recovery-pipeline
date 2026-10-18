from pathlib import Path
lines = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/third_party/cuTAMP/cutamp/particle_initialization.py").read_text(errors="replace").splitlines()
for i in range(188, 250):
    print(f"{i+1}:{lines[i]}")
