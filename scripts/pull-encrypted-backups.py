#!/usr/bin/env python3
"""Copy only the three owner-approved existing encrypted VPS archives; no remote writes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent.parent
ACCESS=ROOT.parent/'.server-access'
NAMES=['20261030T123810Z.tar.gz.age','20261102T091544Z.tar.gz.age','20261103T121905Z.tar.gz.age']

def remote(code):
    args=['ssh','-T','-i',str(ACCESS/'lookin-base-194.135.23.218-ed25519'),
          '-o','IdentitiesOnly=yes','-o','IdentityAgent=none','-o','BatchMode=yes',
          '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile="'+str(ACCESS/'known_hosts')+'"',
          '-o','HostKeyAlgorithms=ssh-ed25519','-o','ConnectTimeout=10',
          'ltadmin@194.135.23.218','sudo -n python3 -']
    p=subprocess.run(args,input=code.encode(),capture_output=True,timeout=60)
    if p.returncode: raise RuntimeError('Remote read failed; response withheld')
    return p.stdout

def main():
    os.umask(0o077)
    folder=ACCESS/'backup-transfer-20261104'
    folder.mkdir(mode=0o700,exist_ok=True)
    result=[]
    for name in NAMES:
        code="""from pathlib import Path
import hashlib,sys
p=Path('/opt/lookin-base/backups/encrypted')/%r
assert not p.is_symlink() and p.is_file() and p.stat().st_size < 100*1024*1024
raw=p.read_bytes()
expected=p.with_name(p.name+'.sha256').read_text().split()[0]
assert hashlib.sha256(raw).hexdigest()==expected
assert raw.startswith(b'age-encryption.org/v1')
sys.stdout.buffer.write(raw)
""" % name
        raw=remote(code)
        digest=hashlib.sha256(raw).hexdigest()
        target=folder/name
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Existing local file differs; refusing overwrite')
        else:
            with target.open('xb') as stream: stream.write(raw)
        checksum=folder/(name+'.sha256')
        if not checksum.exists():
            with checksum.open('x') as stream: stream.write(digest+'  '+name+'\n')
        result.append({'name':name,'bytes':len(raw),'sha256':digest,'local_path':str(target),'server_checksum_verified':True})
    report=ROOT/'local-dev/backup-transfer-2026-11-04.json'
    with report.open('x') as stream: json.dump({'archives':result,'offsite_upload_verified':False},stream,indent=2)
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
