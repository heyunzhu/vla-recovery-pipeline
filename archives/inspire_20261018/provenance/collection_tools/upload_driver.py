from pathlib import Path
import argparse,subprocess,sys,json
p=argparse.ArgumentParser();p.add_argument('--phase',required=True);a=p.parse_args();out=Path(__file__).resolve().parent;request=out/(a.phase+'.private.json')
try:
 subprocess.run([sys.executable,str(out/'upload_lfs_objects.py'),'--request',str(request),'--root',str(out),'--receipt',str(out/(a.phase+'.receipt.json'))],check=True)
finally:
 if request.exists():request.unlink()
