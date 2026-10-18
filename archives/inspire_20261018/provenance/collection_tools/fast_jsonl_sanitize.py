"""JSONL negative-match acceleration; all matching rules remain the original sanitizer."""
from pathlib import Path
import package_ssh_research_assets as p
_base=p.sanitize
def positions(data,needle):
 start=0
 while True:
  at=data.find(needle,start)
  if at<0:return
  yield at;start=at+1
literal_names=[b'apikey',b'api_key',b'api-key',b'accesstoken',b'access_token',b'access-token',b'authtoken',b'auth_token',b'auth-token',b'authkey',b'password',b'passwd',b'clientsecret',b'client_secret',b'client-secret',b'authorization']
token_names=[b'sk-',b'ghp_',b'gho_',b'ghu_',b'ghs_',b'ghr_',b'github_pat_',b'hf_',b'AKIA']
def candidate(data,suffix):
 if suffix!='.jsonl':return _base(data,suffix)
 if b'-----BEGIN ' in data and p.PRIVATE.search(data):return _base(data,suffix)
 lower=data.lower()
 for needle in literal_names:
  for at in positions(lower,needle):
   if p.LITERAL.match(data,at-1 if at and data[at-1] in (34,39) else at):return _base(data,suffix)
 for at in positions(lower,b'environ'):
  if p.ENV_LITERAL.match(data,at):return _base(data,suffix)
 for needle in token_names:
  for at in positions(data,needle):
   if p.TOKEN.match(data,at):return _base(data,suffix)
 return data,0

def install():
 p.sanitize=candidate
