from pathlib import Path
root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/third_party/cuTAMP/cutamp")
def show(name, start, end):
    lines = (root / name).read_text(errors="replace").splitlines()
    print(f"===== {name} {start}-{end} =====")
    for i in range(start - 1, min(end, len(lines))):
        print(f"{i+1}:{lines[i]}")
show("samplers.py", 92, 160)
show("particle_initialization.py", 120, 190)
show("cost_function.py", 250, 310)
