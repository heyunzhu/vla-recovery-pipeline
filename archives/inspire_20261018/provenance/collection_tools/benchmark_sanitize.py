from pathlib import Path
import sys,json,time,hashlib
O=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/github_inspire_archive_20261018');sys.path.insert(0,str(O))
import package_ssh_research_assets as p
original=p.sanitize
hints=[b'apikey',b'api_key',b'api-key',b'access_token',b'access-token',b'accesstoken',b'auth_token',b'auth-token',b'authtoken',b'authkey',b'password',b'passwd',b'secret',b'privatekey',b'private_key',b'private-key',b'private key',b'authorization',b'cookie',b'environ',b'sk-',b'ghp_',b'gho_',b'ghu_',b'ghs_',b'ghr_',b'github_pat_',b'hf_',b'akia',b'\\u']
def positions(data,needle):
 start=0
 while True:
  at=data.find(needle,start)
  if at<0:return
  yield at;start=at+1
literal_names=[b'apikey',b'api_key',b'api-key',b'accesstoken',b'access_token',b'access-token',b'authtoken',b'auth_token',b'auth-token',b'authkey',b'password',b'passwd',b'clientsecret',b'client_secret',b'client-secret',b'authorization']
token_names=[b'sk-',b'ghp_',b'gho_',b'ghu_',b'ghs_',b'ghr_',b'github_pat_',b'hf_',b'AKIA']
def candidate(data,suffix):
 if suffix!='.jsonl':return original(data,suffix)
 if b'-----BEGIN ' in data and p.PRIVATE.search(data):return original(data,suffix)
 lower=data.lower()
 for needle in literal_names:
  for at in positions(lower,needle):
   if p.LITERAL.match(data,at-1 if at and data[at-1] in (34,39) else at):return original(data,suffix)
 for at in positions(lower,b'environ'):
  if p.ENV_LITERAL.match(data,at):return original(data,suffix)
 for needle in token_names:
  for at in positions(data,needle):
   if p.TOKEN.match(data,at):return original(data,suffix)
 return data,0

fixtures=[b'normal robot states 1.2 -3.4',b'{"pass\\u0077ord":"value_must_redact"}',b'{"password":"value_must_redact"}',b'api-key: value_must_redact',b"os.environ['SOME_KEY'] = 'value_must_redact'",b'-----BEGIN OPENSSH PRIVATE KEY-----',b'{"cookie":"value_must_redact"}',b'sk-abcdefghijklmnopqrstuvwxyz123456']
for key in [b'apikey',b'api_key',b'api-key',b'access_token',b'access-token',b'accesstoken',b'auth_token',b'auth-token',b'authtoken',b'authkey',b'password',b'passwd',b'client_secret',b'privatekey',b'private_key',b'private-key',b'authorization']:
 fixtures.extend([b'{"'+key+b'":"value_must_redact"}',key.upper()+b' = value_must_redact'])
checks=0
for suffix in p.TEXT:
 for data in fixtures:
  assert candidate(data,suffix)==original(data,suffix);checks+=1
R=O.parent.parent;paths=[R/'logs/libero_pro_six_suite_pack36_20260930/libero_goal_task/shards/b/pack/task06/ep19/query_trace.jsonl',R/'logs/continual_skill_core60_pilot_20261006/lanes/lane0/000_C0_libero_goal_swap/run/task01/ep00/episode.json'];rows=[]
for path in paths:
 if not path.exists():continue
 data=path.read_bytes();t=time.monotonic();a=original(data,path.suffix);old=time.monotonic()-t;t=time.monotonic();b=candidate(data,path.suffix);new=time.monotonic()-t;assert a==b;rows.append(dict(path=str(path.relative_to(R)),bytes=len(data),original_sec=old,fast_sec=new,speedup=old/max(new,1e-9),output_equal=True))
report=dict(fixtures_compared=checks,representative_files=rows,all_equal=True);(O/'sanitize_fastpath_benchmark.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
