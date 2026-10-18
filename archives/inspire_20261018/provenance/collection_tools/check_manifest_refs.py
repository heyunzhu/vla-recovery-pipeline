from pathlib import Path
import subprocess,json
r=Path('E:/VLA_recovery_workspace/vla-recovery-ssh-archive');a=r/'archives/inspire_20261018';expected={}
for p in (a/'manifests').glob('*.manifest.json'):
 m=json.loads(p.read_text(encoding='utf-8'))
 for x in m['parts']:expected['archives/inspire_20261018/assets/'+x['name']]=x
actual={x['name']:x for x in json.loads(subprocess.check_output(['git','lfs','ls-files','--json'],cwd=r,text=True))['files'] if x['name'].startswith('archives/inspire_20261018/assets/')}
assert set(actual)==set(expected)
for name,x in expected.items():assert actual[name]['oid']==x['sha256'] and actual[name]['size']==x['bytes'],name
print('EXACT_MANIFEST_REFERENCE_MATCH',len(expected),'part references')
(a/'provenance/git_manifest_reference_verification.json').write_text(json.dumps(dict(parts=len(expected),all_sha256_and_sizes_match=True),indent=2),encoding='utf-8')
