from pathlib import Path
import json,shutil,sys
from transport import download,execute,REMOTE
r=Path('E:/VLA_recovery_workspace/vla-recovery-ssh-archive');a=r/'archives/inspire_20261018';w=Path(__file__).parent
wanted=['archive_plan.json','archive_finished.json','parallel_handoff.json','parallel_status.json','supplemental_plan.json','supplemental_finished.json','historical_skills_scope.json','historical_skills_finished.json','historical_detector_finished.json','detector_artifact_identity.json','root_supplement_scope.json','root_supplement_finished.json','base_model_hashes.json','aws_route_probe.json','history_fast_handoff.json','sanitize_fastpath_benchmark.json','history_fast_prefix_equivalence.json']
code="from pathlib import Path;import json;p=Path("+repr(REMOTE)+");print(json.dumps([x for x in "+repr(wanted)+" if (p/x).exists()]))"
out=execute(code,60);ready=json.loads(out[:out.rfind(']')+1])
if '--partial' not in sys.argv:assert set(ready)==set(wanted),set(wanted)-set(ready)
for n in ready:
 target=a/'provenance'/n
 if not target.exists() or n in ['archive_finished.json','parallel_status.json']:download(REMOTE+'/'+n,target)

for n in ['package_ssh_research_assets.py','upload_lfs_objects.py','collect_worker.py','parallel_supervisor.py','fast_jsonl_sanitize.py','history_finisher.py']:
 download(REMOTE+'/'+n,a/'provenance/collection_tools'/n)
for n in ['transfer.py','root_supplement.py','historical_detector.py','historical_skills.py','verify_remote.py','write_index.py','final_pointers.py','benchmark_sanitize.py','check_fast_prefix.py']:
 shutil.copyfile(w/n,a/'provenance/collection_tools'/n)
print('Final provenance and exact deployed tools saved')
