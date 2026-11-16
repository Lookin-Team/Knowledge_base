#!/usr/bin/env python3
"""Explicit owner-authorized read-only review of the existing VPS; no secret output."""
import datetime
import json
from pathlib import Path
import subprocess
import socket
import ssl
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent.parent
ACCESS = ROOT.parent / '.server-access'
REMOTE = r'''
import datetime,json,pathlib,subprocess,stat
def run(args):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=35)
    return {'code':p.returncode,'output':p.stdout[:24000] if p.returncode==0 else 'Command failed; details withheld'}
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
for name,args in {
 'disk':['df','-h','/opt/lookin-base'],
 'memory':['free','-m'],
 'listeners':['ss','-lnt'],
 'firewall':['ufw','status','verbose'],
 'ssh_effective':['sshd','-T'],
 'timers':['systemctl','list-timers','--all','--no-pager'],
 'failed_services':['systemctl','--failed','--no-pager'],
 'root_crontab':['crontab','-l'],
}.items():
    if name=='root_crontab':
        result=run(args)
        out[name]={'code':result['code'],'noncomment_entries':sum(1 for x in result['output'].splitlines() if x.strip() and not x.lstrip().startswith('#')) if result['code']==0 else None}
    elif name=='ssh_effective':
        result=run(args)
        keys={'permitrootlogin','passwordauthentication','kbdinteractiveauthentication','pubkeyauthentication','allowusers','allowtcpforwarding','allowagentforwarding','x11forwarding'}
        out[name]={'code':result['code'],'output':'\n'.join(x for x in result['output'].splitlines() if x.split()[0] in keys)}
    else: out[name]=run(args)
ids=run(['docker','ps','-aq','--filter','label=com.docker.compose.project=lookin-base'])
containers=[]
for ident in ids['output'].splitlines() if ids['code']==0 else []:
    result=run(['docker','inspect',ident])
    if result['code']!=0: continue
    c=json.loads(result['output'])[0]; h=c['HostConfig']
    containers.append({'name':c['Name'],'image':c['Config']['Image'],'image_id':c['Image'],
      'status':c['State']['Status'],'health':c['State'].get('Health',{}).get('Status'),
      'restart_count':c['RestartCount'],'user':c['Config'].get('User'),
      'read_only':h['ReadonlyRootfs'],'privileged':h['Privileged'],'network_mode':h['NetworkMode'],
      'ports':c['NetworkSettings']['Ports'],'security_opt':h.get('SecurityOpt'),
      'cap_drop':h.get('CapDrop'),'memory_limit':h['Memory'],'pids_limit':h.get('PidsLimit'),
      'restart_policy':h['RestartPolicy'],'log_config':h['LogConfig'],
      'mounts':[{'type':m['Type'],'destination':m['Destination'],'rw':m['RW']} for m in c['Mounts']],
      'networks':list(c['NetworkSettings']['Networks'])})
out['containers']=containers
out['networks']=[]
for name in sorted({n for c in containers for n in c['networks']}):
    result=run(['docker','network','inspect',name])
    if result['code']==0:
        n=json.loads(result['output'])[0]
        out['networks'].append({'name':name,'internal':n['Internal'],'driver':n['Driver']})
out['backup_files']=[]
folder=pathlib.Path('/opt/lookin-base/backups/encrypted')
for p in sorted(folder.glob('*.age')):
    s=p.stat(); out['backup_files'].append({'name':p.name,'bytes':s.st_size,'mtime_utc':datetime.datetime.fromtimestamp(s.st_mtime,datetime.timezone.utc).isoformat(),'mode':oct(stat.S_IMODE(s.st_mode)),'checksum_file_exists':p.with_name(p.name+'.sha256').exists()})
out['backup_work_dirs']=len(list(pathlib.Path('/opt/lookin-base/backups').glob('.work-*')))
out['protected_paths']=[]
for name in ['secrets','secrets/app.env','deploy.env','operations/backup-vps.py']:
    p=pathlib.Path('/opt/lookin-base')/name
    if p.exists():
        s=p.stat(); out['protected_paths'].append({'path':name,'uid':s.st_uid,'mode':oct(stat.S_IMODE(s.st_mode))})
php=r"""require '/app/vendor/autoload.php';
$app=require '/app/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
Illuminate\Support\Facades\DB::statement('SET SESSION TRANSACTION READ ONLY');
Illuminate\Support\Facades\DB::beginTransaction();
$users=[];foreach(BookStack\Users\Models\User::with('roles')->get() as $u){
$users[]=['id'=>$u->id,'roles'=>$u->roles->pluck('id')->all(),'mfa_entries'=>$u->mfaValues()->count()];}
$roles=[];foreach(BookStack\Users\Models\Role::with('permissions')->get() as $r){
$roles[]=['id'=>$r->id,'system_name'=>$r->system_name,'mfa_enforced'=>$r->mfa_enforced,'permissions'=>$r->permissions->pluck('name')->all()];}
$tokens=[];foreach(BookStack\Api\ApiToken::all() as $t){$tokens[]=['record_id'=>$t->id,'user_id'=>$t->user_id,'created_at'=>(string)$t->created_at,'expires_at'=>$t->expires_at->format('Y-m-d'),'expired'=>$t->expires_at->isPast()];}
echo json_encode(['public_access'=>(bool)setting('app-public'),'self_registration'=>(bool)setting('registration-enabled'),'image_storage'=>config('filesystems.images'),'timezone'=>config('app.timezone'),'production'=>config('app.env')==='production','debug'=>config('app.debug'),'secure_cookie'=>config('session.secure'),'mail_driver'=>config('mail.default'),'users'=>$users,'roles'=>$roles,'tokens'=>$tokens]);
Illuminate\Support\Facades\DB::rollBack();"""
cmd=['docker','compose','--env-file','/opt/lookin-base/deploy.env','-f','/opt/lookin-base/server/compose.yaml','exec','-T','app','php','-r',php]
result=run(cmd)
try: out['application']=json.loads(result['output']) if result['code']==0 else {'error':'Read-only application check failed; details withheld'}
except Exception: out['application']={'error':'Unexpected response; details withheld'}
print(json.dumps(out))
'''

def main():
    args=['ssh','-T','-i',str(ACCESS/'lookin-base-194.135.23.218-ed25519'),
          '-o','IdentitiesOnly=yes','-o','IdentityAgent=none','-o','BatchMode=yes',
          '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile="'+str(ACCESS/'known_hosts')+'"',
          '-o','HostKeyAlgorithms=ssh-ed25519','-o','ConnectTimeout=10',
          'ltadmin@194.135.23.218','sudo -n python3 -']
    p=subprocess.run(args,input=REMOTE,text=True,capture_output=True,timeout=180)
    if p.returncode:
        raise SystemExit('SSH review failed: '+p.stderr[:500])
    report=json.loads(p.stdout)
    def probe(port):
        try:
            with socket.create_connection(('194.135.23.218',port),timeout=3):
                return str(port),'open'
        except (OSError,TimeoutError):
            return str(port),'no_connection_from_this_mac'
    with ThreadPoolExecutor(max_workers=4) as pool:
        report['external_tcp']=dict(pool.map(probe,[22,80,443,3306,8080,9000,2019]))
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('https://base.lookin.team/books',timeout=20) as response:
            report['unauthenticated_books']={'status':response.status,'final_path':urllib.parse.urlsplit(response.url).path,'nosniff':response.headers.get('X-Content-Type-Options')}
        with socket.create_connection(('base.lookin.team',443),timeout=10) as connection:
            with ssl.create_default_context().wrap_socket(connection,server_hostname='base.lookin.team') as tls:
                report['tls']={'verified':True,'expires':tls.getpeercert().get('notAfter'),'protocol':tls.version()}
    except Exception:
        report['https_error']='External verification failed; details withheld'
    report['scope']='Read-only inspection; no token secrets, credentials or document contents collected. Application boot may create normal runtime logs/cache.'
    target=ROOT/'local-dev/security-vps-readonly-2026-11-04.json'
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__': main()
