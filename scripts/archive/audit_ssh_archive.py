"""Final credential scrub of completed source/record archives before publication.

Original source files are untouched. If another redaction is needed, previous
archive parts stay under pre_scrub/ on the source server and are not published.
"""
import argparse
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

from package_ssh_research_assets import Parts,HashReader,sanitize,TEXT
from restore_ssh_research_assets import Joined


def audit(root,label):
    p=root/f'{label}.manifest.json';m=json.loads(p.read_text());lookup={f['path']:f for f in m['files']}
    checked=root/'checked';checked.mkdir(exist_ok=True)
    writer=Parts(checked,label);entries=[];findings=[];excluded=list(m['excluded'])
    with Joined([root/x['name'] for x in m['parts']]) as stream:
        with tarfile.open(fileobj=io.BufferedReader(stream),mode='r|gz') as source:
            with gzip.GzipFile(filename='',mode='wb',fileobj=writer,compresslevel=2,mtime=0) as gz:
                with tarfile.open(fileobj=gz,mode='w|',format=tarfile.PAX_FORMAT) as dest:
                    for info in source:
                        if not info.isfile() or info.name not in lookup:raise ValueError('unexpected member')
                        original=lookup[info.name];row=dict(original);suffix=Path(info.name).suffix.lower()
                        if '.py.bak_' in info.name:suffix='.py'
                        with source.extractfile(info) as f:
                            if suffix in TEXT and info.size<=32*1024**2:
                                before=f.read()
                                if hashlib.sha256(before).hexdigest()!=original['sha256']:raise ValueError('input archive corruption')
                                data,n=sanitize(before,suffix)
                                if data is None:
                                    findings.append(dict(path=info.name,reason='private_key_content'));excluded.append(findings[-1]);continue
                                if data!=before:
                                    findings.append(dict(path=info.name,additional_redactions=n));row['redactions']+=n;row['pre_scrub_sha256']=row['sha256']
                                member=copy.copy(info);member.size=len(data);reader=HashReader(io.BytesIO(data));dest.addfile(member,reader);row['archived_bytes']=len(data)
                            else:
                                reader=HashReader(f);dest.addfile(info,reader)
                                if reader.sha.hexdigest()!=original['sha256']:raise ValueError('input archive corruption')
                        row['sha256']=reader.sha.hexdigest();entries.append(row)
    writer.finish()
    if findings:
        backup=root/'pre_scrub';backup.mkdir(exist_ok=True)
        for x in m['parts']:(root/x['name']).rename(backup/x['name'])
        p.rename(backup/p.name)
        for x in writer.parts:(checked/x['name']).rename(root/x['name'])
        m.update(files=entries,excluded=excluded,parts=writer.parts,archive_bytes=sum(x['bytes'] for x in writer.parts),source_bytes=sum(x['source_bytes'] for x in entries),final_credential_audit=True)
        p.write_text(json.dumps(m,ensure_ascii=False,indent=2))
    else:
        for x in writer.parts:
            q=(checked/x['name']).resolve();assert q.is_relative_to(checked.resolve());q.unlink()
    report=dict(label=label,files_checked=len(lookup),additional_findings=findings,rewritten=bool(findings),completed=True)
    (root/f'{label}.security_audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--label',required=True);a=p.parse_args();audit(a.root.resolve(),a.label)
