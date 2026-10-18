"""Upload pre-authorized LFS objects with short-lived per-object upload actions.

The private request file is created separately with mode 0600. It contains only
upload actions, never the account credential or local verify actions. Receipts
contain paths, checksums and HTTP status, never signed URLs or headers.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import http.client
import json
from pathlib import Path
import time
from urllib.parse import urlsplit


def upload(row,root):
    result={k:row[k] for k in ('name','oid','size')}
    p=(root/row['name']).resolve()
    if not p.is_relative_to(root.resolve()):raise ValueError('upload path outside archive root')
    if p.stat().st_size!=row['size']:raise ValueError('size mismatch')
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
    if h.hexdigest()!=row['oid']:raise ValueError('checksum mismatch')
    if not row.get('upload'):return dict(result,already_present=True,success=True)
    action=row['upload'];url=urlsplit(action['href'])
    if url.scheme!='https':raise ValueError('HTTPS required')
    for attempt in range(3):
        connection=None
        try:
            connection=http.client.HTTPSConnection(url.hostname,url.port or 443,timeout=180)
            headers=dict(action.get('header',{}));headers['Content-Length']=str(row['size'])
            with p.open('rb') as f:
                connection.request('PUT',url.path+('?' +url.query if url.query else ''),body=f,headers=headers)
                response=connection.getresponse();status=response.status;response.read(4096)
            if status in (200,201,202,204):return dict(result,http_status=status,success=True,attempt=attempt+1)
            result.update(http_status=status,success=False)
        except Exception as e:result.update(error_type=type(e).__name__,success=False)
        finally:
            if connection:connection.close()
        time.sleep(2+attempt*3)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    requests=json.loads(a.request.read_text(encoding='utf-8'));rows=[];start=time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(upload,row,a.root) for row in requests]
        for f in as_completed(futures):
            try:r=f.result()
            except Exception as e:r=dict(success=False,error_type=type(e).__name__)
            rows.append(r);a.receipt.write_text(json.dumps(dict(complete=False,objects=rows,elapsed_sec=time.time()-start),indent=2), encoding='utf-8');print(json.dumps(r),flush=True)
    a.receipt.write_text(json.dumps(dict(complete=True,objects=rows,success=all(r['success'] for r in rows),elapsed_sec=time.time()-start),indent=2), encoding='utf-8')


if __name__=='__main__':main()
