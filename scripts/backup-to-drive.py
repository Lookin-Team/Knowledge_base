#!/usr/bin/env python3
"""VPS-only weekly encrypted backup and download verification. Never delete copies."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

ROOT = Path('/opt/lookin-base')
CONFIG = ROOT / 'secrets/backup-rclone.conf'
SETTINGS = ROOT / 'operations/drive-backup.json'
RCLONE = '/usr/local/lib/lookin-backup/rclone-v1.76.0'
STATE = ROOT / 'backups/drive-status.json'


def call(args, **kwargs):
    # Rclone's own transfer retries do not cover every quota/list operation.
    # Retry only idempotent Drive commands, never snapshot creation/site pauses.
    attempts = 3 if args[0] == RCLONE else 1
    for attempt in range(attempts):
        try:
            return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=1800, **kwargs)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def checked_config():
    st = CONFIG.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o600:
        raise RuntimeError('Unsafe OAuth configuration permissions')
    import configparser
    c = configparser.ConfigParser(interpolation=None)
    c.read(CONFIG)
    if c['lookin']['scope'] != 'drive.file' or not c['lookin'].get('token'):
        raise RuntimeError('Expected restricted Drive credentials')
    folder = json.loads(SETTINGS.read_text())['folder_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', folder):
        raise RuntimeError('Invalid folder ID')
    return [RCLONE, '--config', str(CONFIG), '--drive-root-folder-id', folder,
            '--retries', '3', '--low-level-retries', '5', '--contimeout', '20s',
            '--timeout', '5m', '--stats', '0', '--log-level', 'ERROR']


def upload_snapshot(base, archive):
    """Require complete local snapshot and verify remote bytes before accepting it."""
    name = archive.name
    if not re.fullmatch(r'\d{8}T\d{6}Z\.tar\.gz\.age', name) or archive.is_symlink():
        raise RuntimeError('Invalid snapshot')
    checksum = archive.with_name(name + '.sha256')
    if checksum.is_symlink():
        raise RuntimeError('Invalid checksum')
    expected = checksum.read_text().split()
    actual = digest(archive)
    if expected != [actual, name]:
        raise RuntimeError('Local checksum mismatch')
    remote = 'lookin:weekly/' + name
    # Immutable refuses to replace an existing different object. Never sync/move/delete.
    call(base + ['copyto', str(archive), remote, '--immutable'])
    h = hashlib.sha256()
    total = 0
    import tempfile
    # Bound transfer time through subprocess.run; stream download to anonymous VPS file.
    # Only encrypted bytes are downloaded, never decrypted or stored on the Mac.
    with tempfile.TemporaryFile(dir=ROOT / 'backups') as output:
        subprocess.run(base + ['cat', remote, '--count', str(archive.stat().st_size + 1)], check=True, stdout=output,
                       stderr=subprocess.PIPE, timeout=1800)
        output.seek(0)
        for chunk in iter(lambda: output.read(1024 * 1024), b''):
            total += len(chunk)
            h.update(chunk)
    if total != archive.stat().st_size or h.hexdigest() != actual:
        raise RuntimeError('Downloaded checksum mismatch')
    call(base + ['copyto', str(checksum), remote + '.sha256', '--immutable'])
    if call(base + ['cat', remote + '.sha256']).stdout != checksum.read_bytes():
        raise RuntimeError('Remote checksum file mismatch')
    return {'snapshot': name, 'bytes': total, 'sha256': actual, 'download_verified': True}


def save_state(value):
    tmp = STATE.with_suffix('.json.partial')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(STATE)


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Root required')
    os.umask(0o077)
    with (ROOT / 'backups/drive-job.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        base = checked_config()  # Fail before pausing the site if auth is missing.
        quota = json.loads(call(base + ['about', 'lookin:', '--json']).stdout)
        if quota.get('free') is not None and quota['free'] < 1024 ** 3:
            raise RuntimeError('Less than 1 GiB free on Drive')
        # Auth/network preflight before creating a snapshot.
        call(base + ['lsjson', 'lookin:', '--max-depth', '1'])
        if len(sys.argv) == 3 and sys.argv[1] == '--existing':
            name = sys.argv[2]
            if not re.fullmatch(r'\d{8}T\d{6}Z\.tar\.gz\.age', name):
                raise RuntimeError('Invalid existing archive name')
            archive = ROOT / 'backups/encrypted' / name
        elif len(sys.argv) == 1:
            result = json.loads(call(['/usr/bin/python3', str(ROOT / 'operations/backup-vps.py')]).stdout)
            archive = Path(result['encrypted_backup'])
            if archive.parent != ROOT / 'backups/encrypted':
                raise RuntimeError('Unexpected backup destination')
        else:
            raise RuntimeError('Invalid arguments')
        result = upload_snapshot(base, archive)
        result.update({'result': 'PASS', 'checked_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'automatic_deletion': False})
        save_state(result)
        print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Preserve the last successful receipt; record failures separately.
        try:
            if os.geteuid() == 0:
                os.umask(0o077)
                (ROOT / 'backups/drive-last-failure.json').write_text(json.dumps({
                    'result': 'FAIL',
                    'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'details': 'Sensitive command output withheld; inspect credentials, quota and availability.'
                }) + '\n')
        except Exception:
            pass
        # Do not print subprocess errors: OAuth details/content must not reach journal.
        print('Weekly Drive backup failed; inspect protected status and service availability.', file=sys.stderr)
        sys.exit(1)
