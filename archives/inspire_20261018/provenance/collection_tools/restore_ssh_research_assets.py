"""Verify multipart archives and optionally extract only verified regular files.

Example:
  python scripts/archive/restore_ssh_research_assets.py \
    --archive archives/ssh_20261018 --label rgbd_dino_full_20261018 \
    --extract /new/project

Requires `git lfs pull` first. Without --extract, streams and verifies content
without creating a second copy. Source mtimes/modes are retained in the tar.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import os
import tarfile


class Joined(io.RawIOBase):
    def __init__(self,paths):self.paths=iter(paths);self.current=None
    def readable(self):return True
    def readinto(self,b):
        while True:
            if self.current is None:
                try:self.current=next(self.paths).open('rb')
                except StopIteration:return 0
            n=self.current.readinto(b)
            if n:return n
            self.current.close();self.current=None
    def close(self):
        if self.current:self.current.close()
        super().close()


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
    return h.hexdigest()


def verify(archive,label,extract=None,include_prefixes=None):
    manifest=json.loads((archive/'manifests'/f'{label}.manifest.json').read_text(encoding='utf-8'))
    paths=[]
    for part in manifest['parts']:
        p=archive/'assets'/part['name']
        if p.stat().st_size!=part['bytes'] or sha(p)!=part['sha256']:
            raise ValueError('part missing, corrupt, or LFS pointer only: '+str(p))
        paths.append(p)
    expected={f['path']:f for f in manifest['files']};seen=set()
    with Joined(paths) as joined,io.BufferedReader(joined,buffer_size=1024**2) as stream:
        with tarfile.open(fileobj=stream,mode='r|gz') as tar:
            for member in tar:
                name=member.name;relative=PurePosixPath(name)
                if not member.isfile() or relative.is_absolute() or '..' in relative.parts or '\\' in name:
                    raise ValueError('unsafe archive member: '+name)
                if name not in expected or name in seen:raise ValueError('unexpected/duplicate member: '+name)
                row=expected[name];h=hashlib.sha256();size=0;out=None
                selected=extract is not None and (not include_prefixes or any(name==p.rstrip('/') or name.startswith(p.rstrip('/')+'/') for p in include_prefixes))
                if selected:
                    dest=(extract/Path(*relative.parts)).resolve()
                    if not dest.is_relative_to(extract.resolve()):raise ValueError('destination escapes extraction root')
                    if dest.exists():raise FileExistsError('refusing to overwrite '+str(dest))
                    dest.parent.mkdir(parents=True,exist_ok=True);out=dest.open('xb')
                try:
                    with tar.extractfile(member) as f:
                        for b in iter(lambda:f.read(8*1024**2),b''):
                            size+=len(b);h.update(b)
                            if out:out.write(b)
                finally:
                    if out:out.close()
                if size!=row['archived_bytes'] or h.hexdigest()!=row['sha256']:
                    raise ValueError('member checksum mismatch: '+name)
                if selected:
                    os.chmod(dest,member.mode & 0o777)
                    os.utime(dest,(member.mtime,member.mtime))
                seen.add(name)
    if seen!=set(expected):raise ValueError('archive incomplete')
    return dict(label=label,files=len(seen),parts=len(paths),archive_bytes=sum(p['bytes'] for p in manifest['parts']),verified=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--label',required=True);p.add_argument('--extract',type=Path);p.add_argument('--include-prefix',action='append')
    a=p.parse_args();print(json.dumps(verify(a.archive,a.label,a.extract,a.include_prefix)))
