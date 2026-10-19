from pathlib import Path
import subprocess,sys,json,datetime,shutil
w=Path(__file__).parent;r=Path('E:/VLA_recovery_workspace/vla-recovery-ssh-archive');a=r/'archives/inspire_20261018'
def step(name,*args):subprocess.run([sys.executable,str(w/name),*args],check=True)
d=json.loads((w/'transfer_state.json').read_text(encoding='utf-8'));assert len(d['complete'])==67 and set(d['complete'])==set(d['dispatched']), 'Final archive has not finished uploading'
if '--metadata-ready' not in sys.argv:step('fetch_final_metadata.py')
step('final_pointers.py')
# Stage only the archive assets so the verifier sees every final LFS reference.
subprocess.run(['git','add','archives/inspire_20261018/assets'],cwd=r,capture_output=True,check=True)
step('check_manifest_refs.py');step('verify_remote.py');step('write_index.py');step('write_hub.py')
idx=json.loads((a/'archive_index.json').read_text(encoding='utf-8'));assert idx['status']=='complete' and not idx['pending_archive_labels']
(a/'provenance/completion.json').write_text(json.dumps(dict(completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),groups=67,temporary_cpu_instance_created=False,source_instance='xinghanbo-eval',original_research_files_modified=False,old_historical_partial_files_excluded=True),indent=2)+'\n',encoding='utf-8')
for name in ['finish.py','check_manifest_refs.py','verify_full_part.py','write_index.py','write_hub.py','fetch_final_metadata.py','transfer.py','final_pointers.py']:
 source=(w/name).read_text(encoding='utf-8-sig');(a/'provenance/collection_tools'/name).write_text('\n'.join(line.rstrip() for line in source.splitlines())+'\n',encoding='utf-8')
subprocess.run(['git','add','archives/README.md','archives/inspire_20261018'],cwd=r,capture_output=True,check=True)
subprocess.run(['git','diff','--cached','--check'],cwd=r,check=True)
step('check_manifest_refs.py')
subprocess.run(['git','add','archives/inspire_20261018/provenance/git_manifest_reference_verification.json'],cwd=r,capture_output=True,check=True)
subprocess.run(['git','commit','--quiet','-m','archive: complete Inspire research assets and verified migration index'],cwd=r,check=True)
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip();print('FINAL_SHA',sha,flush=True)
subprocess.run(['git','push','origin',sha+':refs/heads/codex/inspire-archive-20261018'],cwd=r,check=True)
remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/codex/inspire-archive-20261018'],cwd=r,text=True).split()[0];assert remote==sha
assert not subprocess.check_output(['git','status','--porcelain'],cwd=r,text=True).strip()
(w/'publication_receipt.json').write_text(json.dumps(dict(complete=True,sha=sha,remote_sha=remote,groups=67,unique_new_lfs_object_bytes=idx['unique_new_lfs_object_bytes']),indent=2),encoding='utf-8');print('PUBLICATION_VERIFIED',sha,idx['unique_new_lfs_object_bytes'],flush=True)
