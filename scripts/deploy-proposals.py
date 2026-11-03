#!/usr/bin/env python3
"""Deploy only the reviewed proposal extension over the current immutable VPS release."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

ROOT=Path(__file__).resolve().parent.parent
RELEASE='/opt/lookin-base/releases/proposals-20261103'
IMAGE='lookin-base-app:v26.09.2-proposals20261103-1'
BASE_ID='sha256:7c1563bb372a4a2655a8b5970922bd0964a4392add089982fcf6068499ebeaf6'

def main():
    deploy=runpy.run_path(str(ROOT/'scripts/deploy-vps.py'))
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    archive=subprocess.check_output(['git','archive','--format=tar',revision,'local-dev/theme/functions.php',
        'local-dev/theme/proposals','local-dev/theme/home/default.blade.php','local-dev/theme/lookin/sidebar.blade.php',
        'scripts/install-proposals.php','server/proposals/Dockerfile'],cwd=ROOT)
    deploy['remote']('sudo -n mkdir -p '+RELEASE,capture=True)
    deploy['remote']('sudo -n tar -xf - -C '+RELEASE,data=archive,binary=True,capture=True)
    program=r'''
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/opt/lookin-base'); release=root/'releases/proposals-20261103'
image='lookin-base-app:v26.09.2-proposals20261103-1'
def run(args,**kw):
    kw.setdefault('stdout',subprocess.PIPE);kw.setdefault('stderr',subprocess.PIPE)
    return subprocess.run(args,check=True,timeout=180,**kw)
base=run(['docker','image','inspect','lookin-base-app:v26.09.2-ui20261102-2','--format','{{.Id}}'],text=True).stdout.strip()
assert base=='BASE_ID'
run(['docker','build','--pull=false','--network=none','-f',str(release/'server/proposals/Dockerfile'),'-t',image,str(release)])
for file in ['functions.php','proposals/Proposals.php']:
    run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',image,'php','-l','/app/themes/lookin-base/'+file])
cp=['docker','compose','--env-file',str(root/'deploy.env'),'-f',str(root/'server/compose.yaml')]
config=json.loads(run(cp+['config','--format','json'],text=True).stdout)
assert config['services']['app']['image']=='lookin-base-app:v26.09.2-ui20261102-2'
assert not config['services']['app'].get('ports') and not config['services']['db'].get('ports')
assert config['services']['app']['read_only']
# Preserve exact configuration for rollback without exposing secrets.
envpath=root/'secrets/app.env'; deploypath=root/'deploy.env'
env=envpath.read_text(); deploy=deploypath.read_text()
(release/'app.env.before').write_text(env); (release/'deploy.env.before').write_text(deploy)
for p in [release/'app.env.before',release/'deploy.env.before']: p.chmod(0o600)
php=r''' + '"""' + r'''<?php
require '/app/vendor/autoload.php'; $app=require '/app/bootstrap/app.php'; $app->make(\Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$users=\BookStack\Users\Models\User::orderBy('id')->get();
$access=$users->map(fn($u)=>['id'=>$u->id,'roles'=>$u->roles->pluck('id')->sort()->values()->all()])->all();
echo json_encode(['users_roles'=>hash('sha256',json_encode($access)),'pages'=>\BookStack\Entities\Models\Page::count(),'app_key'=>hash('sha256',config('app.key'))]);
''' + '"""' + r'''
before=json.loads(run(cp+['exec','-T','app','php'],input=php,text=True).stdout)
try:
    lines=[l for l in env.splitlines() if not l.startswith(('LOOKIN_PROPOSAL_AUTHOR_IDS=','LOOKIN_PROPOSAL_MODERATOR_IDS='))]
    envpath.write_text('\n'.join(lines)+'\nLOOKIN_PROPOSAL_AUTHOR_IDS=4,5,6\nLOOKIN_PROPOSAL_MODERATOR_IDS=1\n')
    deploypath.write_text('\n'.join('APP_IMAGE='+image if l.startswith('APP_IMAGE=') else l for l in deploy.splitlines())+'\n')
    run(cp+['config','--quiet'])
    # Additive tables only, executed in a one-shot container, never in a restart loop.
    run(cp+['run','--rm','--no-deps','app','php','scripts/install-proposals.php'])
    run(cp+['up','-d','--no-deps','--wait','app'])
    run(cp+['exec','-T','app','php','artisan','view:clear'])
    after=json.loads(run(cp+['exec','-T','app','php'],input=php,text=True).stdout)
    assert before==after
except BaseException:
    envpath.write_text(env); deploypath.write_text(deploy)
    run(cp+['up','-d','--no-deps','--wait','app'])
    raise
(release/'git-commit').write_text('REVISION\n')
report={'image':image,'base_image_id':base,'image_id':run(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).stdout.strip(),
        'git_commit':'REVISION','existing_pages_users_roles_and_app_key_preserved':before==after,'author_ids':[4,5,6],'moderator_ids':[1],'table_install':'PASS','app_health':'PASS'}
(release/'deployment.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
'''.replace('BASE_ID',BASE_ID).replace('REVISION',revision)
    result=deploy['remote']('sudo -n python3 -',data=program,capture=True)
    report=json.loads(result.stdout)
    (ROOT/'local-dev/proposals-deployment-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
