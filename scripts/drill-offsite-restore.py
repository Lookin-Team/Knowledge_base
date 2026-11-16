#!/usr/bin/env python3
"""Restore a verified offsite snapshot in an isolated, disposable local Docker project."""
import base64
import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import subprocess
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
ACCESS = ROOT.parent / '.server-access'
SNAPSHOT = '20261103T121905Z.tar.gz.age'
APP_IMAGE = 'lookin-base-app:v26.09.2-ui20261102-2'
WEB_IMAGE = 'lookin-base-web:v26.09.2-20261030-1'
MYSQL_IMAGE = 'sha256:a0225d1ea6631c8bc2385dc4c2faba17bbf1834ecf369e1659a9a382bd8d5dd7'
AGE = '/private/tmp/lookin-age-1.3.2/age'


def checked(args, **kwargs):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=kwargs.pop('timeout', 180), **kwargs)
    if p.returncode:
        diagnostic = re.search(rb'HTTP check failed: [a-z_]+',p.stderr)
        if diagnostic: raise RuntimeError(diagnostic.group().decode())
        raise RuntimeError('Command failed; protected output withheld')
    return p.stdout


def safe_members(archive):
    for member in archive:
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
            raise RuntimeError('Unsafe backup member')
        yield member


def archive_bytes(archive, name):
    member = archive.getmember(name)
    if not member.isfile() or member.size > 100 * 1024**2:
        raise RuntimeError('Unexpected backup member')
    return archive.extractfile(member).read()


def main():
    os.umask(0o077)
    started = time.monotonic()
    if checked(['docker','context','show']).decode().strip() != 'desktop-linux' or os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        raise SystemExit('Only the local Docker Desktop context is supported')
    receipt = json.loads((ROOT/'local-dev/backup-transfer-2026-11-04.json').read_text())
    record = next(row for row in receipt['archives'] if row['name'] == SNAPSHOT)
    encrypted = ACCESS/'backup-transfer-20261104'/(SNAPSHOT+'.download-verified')
    if not record['drive_download_sha256_verified'] or hashlib.sha256(encrypted.read_bytes()).hexdigest() != record['sha256']:
        raise SystemExit('External backup verification failed')
    payload = checked([AGE,'-d','-i',str(ACCESS/'recovery/backup-age-identity.txt'),str(encrypted)])
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        members = {m.name for m in safe_members(archive)}
        if members != {'manifest.json','database.sql','configuration.tar.gz','uploads.tar.gz'}:
            raise RuntimeError('Unexpected archive layout')
        manifest = json.loads(archive_bytes(archive,'manifest.json'))
        files = {name:archive_bytes(archive,name) for name in members-{'manifest.json'}}
    if manifest['format'] != 'lookin-vps-1' or manifest['sha256'] != {n:hashlib.sha256(v).hexdigest() for n,v in files.items()}:
        raise RuntimeError('Internal archive checksums differ')
    with tarfile.open(fileobj=io.BytesIO(files['configuration.tar.gz'])) as config:
        list(safe_members(config))
        env = archive_bytes(config,'secrets/app.env').decode()
        deploy = archive_bytes(config,'deploy.env').decode()
    key = re.search(r'^APP_KEY=(base64:[A-Za-z0-9+/=]+)$',env,re.M).group(1)
    if len(base64.b64decode(key[7:],validate=True)) != 32 or f'APP_IMAGE={APP_IMAGE}' not in deploy.splitlines() or f'WEB_IMAGE={WEB_IMAGE}' not in deploy.splitlines():
        raise RuntimeError('Snapshot key or release mismatch')
    with tarfile.open(fileobj=io.BytesIO(files['uploads.tar.gz'])) as uploads:
        upload_members = list(safe_members(uploads))
        if not all(m.name == 'storage' or m.name.startswith(('storage/','public/uploads')) for m in upload_members):
            raise RuntimeError('Unexpected uploads archive path')
    source = json.loads((ACCESS/'restore-drill-20261104/image-source.json').read_text())
    app_info = json.loads(checked(['docker','image','inspect',APP_IMAGE]))[0]
    if source['tag'] != APP_IMAGE or app_info['Id'] != source['image_id']:
        raise RuntimeError('Local app image does not match VPS source image')
    for image in (WEB_IMAGE,MYSQL_IMAGE): checked(['docker','image','inspect',image])
    print('External snapshot, internal checksums and matching app image verified',flush=True)

    password, root_password = secrets.token_hex(24), secrets.token_hex(24)
    project = 'lookin-recovery-' + secrets.token_hex(8)
    common = {'read_only':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
              'pids_limit':128,'pull_policy':'never','logging':{'driver':'none'}}
    db = dict(common,image=MYSQL_IMAGE,platform='linux/amd64',networks=['database'],
              cap_add=['CHOWN','DAC_OVERRIDE','FOWNER','SETGID','SETUID'],mem_limit='768m',
              volumes=['database:/var/lib/mysql'],tmpfs=['/var/run/mysqld:uid=999,gid=999,size=16m','/tmp:size=64m'],
              environment={'MYSQL_DATABASE':'bookstack','MYSQL_USER':'bookstack','MYSQL_PASSWORD':password,'MYSQL_ROOT_PASSWORD':root_password},
              command=['--innodb-buffer-pool-size=128M','--performance-schema=OFF','--mysqlx=OFF'],
              healthcheck={'test':['CMD-SHELL','MYSQL_PWD="$$MYSQL_PASSWORD" mysql -h 127.0.0.1 -u bookstack bookstack -e "SELECT 1" >/dev/null'],'interval':'3s','timeout':'4s','retries':50})
    app_env = dict(APP_ENV='production',APP_DEBUG='false',APP_URL='http://web',APP_KEY=key,APP_THEME='lookin-base',
                   DB_CONNECTION='mysql',DB_HOST='db',DB_DATABASE='bookstack',DB_USERNAME='bookstack',DB_PASSWORD=password,
                   STORAGE_TYPE='local',STORAGE_IMAGE_TYPE='local_secure_restricted',SESSION_SECURE_COOKIE='false',SESSION_DRIVER='file',
                   QUEUE_CONNECTION='sync',DISABLE_EXTERNAL_SERVICES='true',ALLOW_UNTRUSTED_SERVER_FETCHING='false',MAIL_DRIVER='array',
                   MAIL_FROM='restore@example.test',API_REQUESTS_PER_MIN='120')
    app = dict(common,image=APP_IMAGE,platform='linux/amd64',user='1000:1000',networks=['database','application'],
               mem_limit='512m',environment=app_env,volumes=['storage:/app/storage','public_uploads:/app/public/uploads'],
               tmpfs=['/app/bootstrap/cache:uid=1000,gid=1000,mode=0770,size=16m','/tmp:mode=1777,size=96m'],
               healthcheck={'test':['CMD','php','-r','$$s=@fsockopen("127.0.0.1",9000,$$e,$$m,2);exit($$s?0:1);'],'interval':'3s','timeout':'4s','retries':30})
    web = dict(common,image=WEB_IMAGE,platform='linux/amd64',user='1000:1000',networks=['application'],
               cap_add=['NET_BIND_SERVICE'],mem_limit='128m',environment={'SITE_ADDRESS':'http://:80','ACME_EMAIL':'restore@example.test'},
               volumes=['public_uploads:/srv/public/uploads:ro','caddy_data:/data','caddy_config:/config'],tmpfs=['/tmp:size=32m'])
    compose = {'services':{'db':db,'app':app,'web':web},'networks':{n:{'internal':True} for n in ('database','application')},
               'volumes':{n:{} for n in ('database','storage','public_uploads','caddy_data','caddy_config')}}
    expected = manifest['table_counts']
    if not all(re.fullmatch(r'[A-Za-z0-9_]+',n) for n in expected): raise RuntimeError('Invalid table identifiers')
    report = {'snapshot':SNAPSHOT,'snapshot_sha256':record['sha256'],'source':'downloaded Google Drive bytes',
              'encrypted_and_internal_hashes':'PASS','original_app_key_preserved':True,'matching_app_image_id':app_info['Id'],
              'working_vps_changed':False,'ports_published':0,'external_networks':0,'mail_driver':'array'}
    with tempfile.TemporaryDirectory(prefix='isolated-restore-',dir=ACCESS) as tmp:
        config = Path(tmp)/'compose.json'
        config.write_text(json.dumps(compose))
        base = ['docker','compose','-p',project,'-f',str(config)]
        def run(*args, **kwargs): return checked(base+list(args),**kwargs)
        def php(code): return run('exec','-T','app','php',input=code.encode())
        def mysql(sql):
            return run('exec','-T','db','sh','-ec','MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -u bookstack -N -B bookstack',input=sql)
        stage = 'database startup'
        try:
            run('config','--quiet')
            run('up','-d','--wait','db')
            stage = 'database restore and counts'
            mysql(files['database.sql'])
            sql='\n'.join(f"SELECT '{n}',COUNT(*) FROM `{n}`;" for n in expected).encode()
            actual = {n:int(v) for n,v in (line.split('\t') for line in mysql(sql).decode().splitlines())}
            if actual != expected: raise RuntimeError('Table row counts differ')
            report.update(restored_table_counts='PASS',tables_checked=len(actual),snapshot_attachments=actual.get('attachments',0),
                          snapshot_contains_proposals='lookin_publication_proposals' in actual)
            print(f'Database restored: counts match all {len(actual)} tables',flush=True)
            stage = 'application and uploads'
            run('up','-d','--wait','app')
            run('exec','-T','app','tar','-xzf','-','-C','/app',input=files['uploads.tar.gz'])
            report['uploads_archive_restored']='PASS'
            stage = 'snapshot content inventory'
            before_pages = mysql(b"SELECT e.id FROM entities e JOIN entity_page_data p ON p.page_id=e.id WHERE e.type='page' AND e.deleted_at IS NULL AND p.draft=0 ORDER BY e.id LIMIT 1;").decode().strip()
            local_attachments = []
            rows = mysql(b'SELECT id,HEX(path) FROM attachments WHERE external=0 ORDER BY id;').decode().splitlines()
            with tarfile.open(fileobj=io.BytesIO(files['uploads.tar.gz'])) as uploads:
                for row in rows:
                    attachment_id, hex_path = row.split('\t')
                    path = PurePosixPath(bytes.fromhex(hex_path).decode().lstrip('/'))
                    if '..' in path.parts or path.parts[:2] != ('uploads','files'):
                        raise RuntimeError('Unexpected local attachment path')
                    raw = archive_bytes(uploads,'storage/'+str(path))
                    local_attachments.append({'id':int(attachment_id),'sha256':hashlib.sha256(raw).hexdigest()})
            report['snapshot_local_attachments']=len(local_attachments)
            stage = 'web startup and runtime network inspection'
            run('up','-d','web')
            for ident in run('ps','-q').decode().splitlines():
                info = json.loads(checked(['docker','inspect',ident]))[0]
                if any(info['NetworkSettings']['Ports'].values()): raise RuntimeError('A test port was published')
                for network in info['NetworkSettings']['Networks']:
                    if not json.loads(checked(['docker','network','inspect',network]))[0]['Internal']:
                        raise RuntimeError('Noninternal network found')
            report['runtime_network_isolation']='PASS'
            stage = 'private mode and local test identity'
            privacy = (ROOT/'server/release-check.php').read_text().replace('http://127.0.0.1:8082','http://web')
            php(privacy)
            # This fixture modifies only the restored copy; no production passwords or keys are used for login.
            fixture_code = (ROOT/'server/tests/fixtures.php').read_text().replace('http://127.0.0.1:8082','http://web')
            fixture_code = fixture_code.replace('$admin->save();','$admin->save();\n\\BookStack\\Api\\ApiToken::query()->delete();\n$admin->mfaValues()->delete();')
            fixture = json.loads(php(fixture_code))
            stage = 'local HTTP login, permissions and attachments'
            config_json = json.dumps(dict(fixture,existing_page=int(before_pages) if before_pages else None,
                                          existing_attachments=local_attachments))
            report.update(json.loads(php('<?php\n$x=json_decode(base64_decode("'+base64.b64encode(config_json.encode()).decode()+'"),true);\n'+HTTP_TEST)))
            report['result']='PASS'
        except Exception as error:
            report.update(result='FAIL',stage=stage,error_type=type(error).__name__)
            if str(error).startswith('HTTP check failed: '): report['http_failure']=str(error)
        finally:
            try:
                run('down','--volumes','--remove-orphans')
                report['temporary_containers_and_volumes_removed']=True
            except Exception:
                report.update(result='FAIL',temporary_containers_and_volumes_removed=False)
    report.update(elapsed_seconds=round(time.monotonic()-started),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  separate_fresh_host_recovery_tested=False,production_dns_switch_tested=False)
    target=ROOT/'local-dev'/'offsite-restore-drill-2026-11-05.json'
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if report['result']!='PASS': raise SystemExit(1)


HTTP_TEST = r'''
function request(string $path, array $headers=[], ?array $form=null, bool $cookies=false, string $method='GET'): array {
    static $browser=null;
    $curl=$cookies ? ($browser ??= curl_init()) : curl_init();
    curl_setopt_array($curl,[CURLOPT_URL=>'http://web'.$path,CURLOPT_RETURNTRANSFER=>true,CURLOPT_FOLLOWLOCATION=>false,
        CURLOPT_CONNECTTIMEOUT=>3,CURLOPT_TIMEOUT=>20,CURLOPT_HTTPHEADER=>$headers,CURLOPT_CUSTOMREQUEST=>$method]);
    if ($cookies) curl_setopt($curl,CURLOPT_COOKIEFILE,'');
    if ($form !== null) curl_setopt($curl,CURLOPT_POSTFIELDS,http_build_query($form));
    elseif ($method==='GET') curl_setopt($curl,CURLOPT_HTTPGET,true);
    $body=curl_exec($curl);
    return [curl_getinfo($curl,CURLINFO_RESPONSE_CODE),$body,curl_getinfo($curl,CURLINFO_REDIRECT_URL)];
}
function requireTrue($ok, string $label): void { if (!$ok) throw new RuntimeException('HTTP check failed: '.$label); }
for ($i=0;$i<30;$i++) { if (request('/login')[0]===200) break; usleep(500000); }
$guest=request('/books'); requireTrue($guest[0]===302 && str_ends_with($guest[2],'/login'),'guest');
$login=request('/login',[],null,true);
requireTrue($login[0]===200 && preg_match('/name="_token"\s+value="([^"]+)"/',$login[1],$match),'login_form');
$posted=request('/login',[],['_token'=>html_entity_decode($match[1]),'email'=>$x['admin_email'],'password'=>$x['admin_password']],true,'POST');
requireTrue($posted[0]===302 && !str_ends_with($posted[2],'/login'),'login_post');
requireTrue(request('/books',[],null,true)[0]===200,'authenticated_books');
$headers=['Authorization: Token '.$x['token_id'].':'.$x['token_secret'],'Accept: application/json'];
if ($x['existing_page'] !== null) requireTrue(request('/api/pages/'.$x['existing_page'],$headers)[0]===200,'existing_page');
foreach ($x['existing_attachments'] as $item) {
    $original=request('/api/attachments/'.$item['id'],$headers);
    $raw=base64_decode(json_decode($original[1],true)['content'] ?? '',true);
    requireTrue($original[0]===200 && is_string($raw) && hash('sha256',$raw)===$item['sha256'],'restored_attachment');
}
$file=request('/api/attachments/'.$x['attachment_id'],$headers);
requireTrue($file[0]===200 && base64_decode(json_decode($file[1],true)['content'],true)==="Lookin release synthetic attachment\n",'synthetic_attachment');
requireTrue(request('/api/users',$headers)[0]===403,'admin_api_denied');
requireTrue(request('/api/pages/'.$x['page_id'],$headers,null,false,'DELETE')[0]===403,'delete_denied');
echo json_encode(['guest_access_denied'=>'PASS','test_admin_login'=>'PASS','existing_page_read'=>$x['existing_page']===null?'not_present':'PASS',
    'restored_attachments_verified'=>count($x['existing_attachments']),
    'synthetic_attachment_download_bytes_match'=>'PASS','reader_admin_and_delete_denied'=>'PASS']);
'''

if __name__ == '__main__': main()
