"""Read-only, explicit-scope research archive; writes only under --output.

Archives are gzip tar streams split into <=1 GB parts for Git LFS. Joining parts
in lexical order reconstructs one tar.gz. Credentials/caches/environments are
excluded; selected textual assets are sanitized before archiving. Source files
are never edited. Each archived regular file has a content checksum.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time

TEXT={'.py','.md','.yaml','.yml','.json','.jsonl','.txt','.sh','.bash','.toml','.cfg','.ini','.xml','.bddl','.csv','.patch','.diff','.rst','.log','.gitignore','.gitattributes'}
SOURCE=TEXT|{'.png','.jpg','.jpeg','.svg','.obj','.stl','.urdf','.npy','.npz','.primitives','.init','.gitkeep'}
PRUNE={'.git','.ssh','.cache','__pycache__','.pytest_cache','node_modules','site-packages','.venv','envs','wandb','native_env'}
SECRET_NAME=re.compile(r'(^\.env($|\.)|\.pem$|\.key$|^id_(rsa|ed25519)|web_session|credentials|policy_endpoint|\.tiptop_llm_env)',re.I)
KEY=re.compile(r'(?:^|[_-])(?:api[_-]?key|access[_-]?token|auth[_-]?token|authkey|password|passwd|secret|private[_-]?key|authorization|cookie)$',re.I)
LITERAL=re.compile(rb'''(?i)(["']?(?:api[_-]?key|access[_-]?token|auth[_-]?token|authkey|password|passwd|client[_-]?secret|authorization)["']?\s*[:=]\s*)(["'])([^\r\n"']{8,})\2''')
TOKEN=re.compile(rb'(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})(?![A-Za-z0-9])')
PRIVATE=re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----')
ENV_LITERAL=re.compile(rb'''(?i)(\benviron\s*\[\s*["'][^"'\r\n]*(?:KEY|TOKEN|PASSWORD|SECRET)[^"'\r\n]*["']\s*\]\s*=\s*)(["'])([^\r\n"']{8,})\2''')
PLAIN=re.compile(rb'''(?mi)^([+ \t-]*(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|auth[_-]?token|authkey|password|passwd|client[_-]?secret|authorization)\s*[:=]\s*)([^"'\s][^\s#]{7,})([^\r\n]*)(\r?)$''')


def sanitize(data, suffix):
    if suffix not in TEXT:return data,0
    if PRIVATE.search(data):return None,1
    count=0
    if suffix=='.json':
        try:
            def clean(v):
                nonlocal count
                if isinstance(v,dict):
                    out={}
                    for k,x in v.items():
                        if KEY.search(k) and isinstance(x,(str,dict,list)) and x:
                            out[k]='<REDACTED>';count+=1
                        else:out[k]=clean(x)
                    return out
                if isinstance(v,list):return [clean(x) for x in v]
                return v
            obj=json.loads(data);obj=clean(obj)
            if count:data=(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()
        except (ValueError,UnicodeDecodeError):pass
    def replace(m):
        value=m[3]
        if any(s in value.lower() for s in (b'os.environ',b'getenv',b'example',b'your_',b'placeholder',b'redacted')):return m[0]
        return m[1]+m[2]+b'<REDACTED>'+m[2]
    before=data;data=LITERAL.sub(replace,data)
    count+=int(before!=data)
    before=data;data=ENV_LITERAL.sub(replace,data);count+=int(before!=data)
    def plain(m):
        value=m[2].lower()
        if any(s in value for s in (b'redacted',b'os.',b'getenv',b'${',b'example',b'your_',b'optional[',b'none')):return m[0]
        return m[1]+b'<REDACTED>'+m[3]+m[4]
    if suffix in {'.yaml','.yml','.ini','.cfg','.txt','.sh','.bash','.toml','.log'}:
        before=data;data=PLAIN.sub(plain,data);count+=int(before!=data)
    data,n=TOKEN.subn(b'<REDACTED_TOKEN>',data);count+=n
    return data,count


class Parts:
    def __init__(self,output,label,limit=1_000_000_000):
        self.output=output;self.label=label;self.limit=limit;self.parts=[];self.f=None;self.total=0
    def write(self,b):
        n=len(b);self.total+=n
        while b:
            if self.f is None:
                self.path=self.output/f'{self.label}.tar.gz.part{len(self.parts):03d}'
                self.f=self.path.open('wb');self.sha=hashlib.sha256();self.size=0
            piece=b[:self.limit-self.size];self.f.write(piece);self.sha.update(piece);self.size+=len(piece);b=b[len(piece):]
            if self.size==self.limit:self.finish()
        return n
    def finish(self):
        if self.f:
            self.f.close();self.parts.append(dict(name=self.path.name,bytes=self.size,sha256=self.sha.hexdigest()));self.f=None
    def flush(self):
        if self.f:self.f.flush()
    def tell(self):return self.total


class HashReader:
    def __init__(self,f):self.f=f;self.sha=hashlib.sha256()
    def read(self,n=-1):
        b=self.f.read(n);self.sha.update(b);return b


def files(root,roots,kind,excluded):
    seen=set()
    for top in roots:
        if not top.exists():continue
        walk=[(str(top.parent),[],[top.name])] if top.is_file() else os.walk(top,followlinks=False)
        for base,dirs,names in walk:
            dirs[:]=sorted(d for d in dirs if d not in PRUNE and not SECRET_NAME.search(d))
            if kind=='source':dirs[:]=[d for d in dirs if d not in {'logs','outputs','rollouts','.ipynb_checkpoints'}]
            if kind=='history':
                dirs[:]=[d for d in dirs if d not in {'runtime_repo','runtime_overlay','code','frozen_runtime','snapshots','resident_vision','images','images640','instance_masks640','states','frames','dino','sam2','downloads','transformers_replace_backup_20260831_204902'}]
            for name in sorted(names):
                p=Path(base)/name;rel=p.relative_to(root).as_posix()
                if rel in seen:continue
                seen.add(rel)
                if '\\' in rel or '..' in Path(rel).parts:
                    excluded.append(dict(path=rel,reason='unsafe_or_nonportable_path'));continue
                if SECRET_NAME.search(name):excluded.append(dict(path=rel,reason='credential_or_runtime_auth_file'));continue
                try:
                    if p.is_symlink() and not p.resolve().is_relative_to(root):
                        excluded.append(dict(path=rel,reason='external_symlink',target=str(p.resolve())));continue
                    if not p.is_file():continue
                    size=p.stat().st_size;suffix=p.suffix.lower()
                    if kind=='source' and (suffix not in SOURCE and name not in {'LICENSE','Dockerfile','requirements.txt','CMakeLists.txt'}):continue
                    if kind=='source' and size>32*1024**2:
                        excluded.append(dict(path=rel,reason='source_file_over_32MiB',bytes=size));continue
                    if kind=='history':
                        if suffix not in TEXT|{'.png','.svg'}:continue
                        if suffix=='.log' and ('rgbd_dino_' not in rel or size>8*1024**2):continue
                        if size>16*1024**2:
                            excluded.append(dict(path=rel,reason='historical_text_over_16MiB',bytes=size));continue
                    yield p
                except OSError as e:excluded.append(dict(path=rel,reason='read_error',error=str(e)))


def package(root,out,label,roots,kind):
    manifest_path=out/f'{label}.manifest.json'
    if manifest_path.exists():return json.loads(manifest_path.read_text(encoding='utf-8'))
    if list(out.glob(f'{label}.tar.gz.part*')):raise RuntimeError('partial archive exists; preserve or inspect before restart: '+label)
    start=time.time();writer=Parts(out,label);entries=[];excluded=[]
    with gzip.GzipFile(filename='',mode='wb',fileobj=writer,compresslevel=2,mtime=0) as gz:
        with tarfile.open(fileobj=gz,mode='w|',format=tarfile.PAX_FORMAT) as tar:
            for p in files(root,roots,kind,excluded):
                rel=p.relative_to(root).as_posix();st=p.stat();info=tarfile.TarInfo(rel);info.size=st.st_size;info.mode=0o755 if os.access(p,os.X_OK) else 0o644;info.mtime=int(st.st_mtime)
                changes=0
                if p.suffix.lower() in TEXT and st.st_size<=32*1024**2:
                    original=p.read_bytes();data,changes=sanitize(original,p.suffix.lower())
                    if data is None:excluded.append(dict(path=rel,reason='private_key_content'));continue
                    info.size=len(data);reader=HashReader(io.BytesIO(data));tar.addfile(info,reader)
                else:
                    with p.open('rb') as f:reader=HashReader(f);tar.addfile(info,reader)
                entries.append(dict(path=rel,source_bytes=st.st_size,archived_bytes=info.size,sha256=reader.sha.hexdigest(),redactions=changes,source_mtime=st.st_mtime))
                if len(entries)%250==0:(out/'status.json').write_text(json.dumps(dict(stage=label,files=len(entries),source_bytes=sum(e['source_bytes'] for e in entries),unix=time.time())), encoding='utf-8')
    writer.finish()
    manifest=dict(schema_version=1,label=label,source_root=str(root),format='gzip tar stream; concatenate numbered parts in lexical order',files=entries,excluded=excluded,parts=writer.parts,elapsed_sec=time.time()-start,source_bytes=sum(e['source_bytes'] for e in entries),archive_bytes=sum(e['bytes'] for e in writer.parts))
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2), encoding='utf-8');print('PACKAGED',label,len(entries),manifest['archive_bytes'],flush=True)
    return manifest


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--group',choices=['small','datasets','uncertainty'],required=True)
    a=ap.parse_args();root=a.root.resolve();out=a.output.resolve();assert out.is_relative_to(root);out.mkdir(parents=True,exist_ok=True)
    if a.group=='small':
        sources=[root/n for n in ['openvla-oft','openpi','ASPIRE','LIBERO-PRO','LIBERO_src','LIBERO-Pro-official-c86fc3b8','code_snapshots','overlays','vla-recovery-pipeline-smoke-f143706','vla-recovery-task10-20260929','libero_config','libero_config_pro']]
        sources += [p for p in root.iterdir() if p.name.startswith('openvla-oft_') and p.is_dir()]
        sources += [p for p in root.iterdir() if p.is_file() and p.suffix in TEXT]
        package(root,out,'source-and-skills',sources,'source')
        history=[p for p in (root/'logs').iterdir() if p.is_dir() and p!=out]
        history += [root/'models/rgbd_dino_finetune_20261015',root/'models/rgbd_dino_full_20261018']
        package(root,out,'experiment-records',history,'history')
    elif a.group=='datasets':
        for name in ['rgbd_dino_20261015','rgbd_dino_full_20261018']:
            package(root,out,name,[root/'datasets'/name],'dataset')
    else:
        for step in ['500','999']:
            p=root/'checkpoints/openpi_jax_uncertainty/pi0_libero_uncertainty_head_only/pi0_libero_uncertainty_headonly_frombase_1k_offline_20260810'/step
            package(root,out,'uncertainty-step'+step,[p],'checkpoint')
    (out/(a.group+'.finished.json')).write_text(json.dumps(dict(group=a.group,unix=time.time())), encoding='utf-8')


if __name__=='__main__':main()
