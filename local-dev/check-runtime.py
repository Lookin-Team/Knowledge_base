"""Read-only runtime checks. Requires running app/db and Docker access."""
import json
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKER = shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'

def run(*args):
    return subprocess.check_output([DOCKER, *args], cwd=ROOT, text=True)

report = {}
for service in ('app', 'db', 'web'):
    cid = run('compose', '-f', 'compose.local.yaml', 'ps', '-q', service).strip()
    assert cid, f'{service}: not running'
    item = json.loads(run('inspect', cid))[0]
    assert item['State']['Running'], f'{service}: not running'
    assert not item['HostConfig']['Privileged']
    assert item['HostConfig']['NetworkMode'] != 'host'
    bindings = item['HostConfig'].get('PortBindings') or {}
    if service == 'web':
        assert bindings == {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8080'}]}, bindings
        assert item['Config']['User'] == '1000:1000'
        assert 'ALL' in item['HostConfig']['CapDrop']
    else:
        assert not bindings, bindings
    if service in ('app', 'web'):
        assert item['Config']['User'] == '1000:1000'
        assert 'ALL' in item['HostConfig']['CapDrop']
    if service == 'web':
        assert item['HostConfig']['ReadonlyRootfs'] is True
    for mount in item['Mounts']:
        if mount['Type'] == 'bind':
            source = Path(mount['Source']).resolve()
            # Docker Desktop represents Mac bind sources with a VM /host_mnt prefix.
            if platform.system() == 'Darwin' and source.parts[:2] == ('/', 'host_mnt'):
                source = Path('/').joinpath(*source.parts[2:]).resolve()
            assert source == ROOT or ROOT in source.parents, source
        assert mount['Destination'] != '/var/run/docker.sock'
    networks = list(item['NetworkSettings']['Networks'])
    assert len(networks) == (2 if service == 'web' else 1), networks
    for name in networks:
        internal = json.loads(run('network', 'inspect', name))[0]['Internal']
        assert internal is True or (service == 'web' and name == 'bookstack-local_ingress'), name
    report[service] = {
        'running': True,
        'user': item['Config']['User'],
        'port_bindings': bindings,
        'networks': networks,
        'mounts': [{'type': m['Type'], 'source': m['Source'], 'target': m['Destination']} for m in item['Mounts']],
    }
report['php_version'] = run('compose', '-f', 'compose.local.yaml', 'exec', '-T', 'app', 'php', '-r', 'echo PHP_VERSION;').strip()
report['upload_progress'] = run('compose', '-f', 'compose.local.yaml', 'exec', '-T', 'app', 'php', '-r', 'echo ini_get("session.upload_progress.enabled");').strip()
assert report['upload_progress'] in ('', '0')
# A single short outbound connection probe: no credentials or data are sent.
probe = '$s=@fsockopen("1.1.1.1",443,$n,$m,3);if($s){fclose($s);exit(1);}echo "blocked";'
report['outbound_tcp_probe'] = run('compose', '-f', 'compose.local.yaml', 'exec', '-T', 'app', 'php', '-r', probe).strip()
assert report['outbound_tcp_probe'] == 'blocked'
print(json.dumps(report, ensure_ascii=False, indent=2))
