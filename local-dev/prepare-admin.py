"""Generate local-only administrator credentials without overwriting existing files."""
from pathlib import Path
import json
import os
import secrets
root = Path(__file__).resolve().parent.parent
private = root / 'local-dev/private'
private.mkdir(mode=0o700, exist_ok=True)
if (private / 'admin.json').exists() or (private / 'login.txt').exists():
    raise SystemExit('Local credentials already exist; refusing to overwrite them.')
credentials = {'email': 'local-admin@example.test', 'password': secrets.token_urlsafe(24)}
contents = {
    'admin.json': json.dumps(credentials) + '\n',
    'login.txt': 'Local BookStack: http://127.0.0.1:8080\nEmail: ' + credentials['email'] + '\nPassword: ' + credentials['password'] + '\nSynthetic local credentials only. Never reuse for production.\n',
}
for name, text in contents.items():
    fd = os.open(private / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
print('Synthetic local credentials created in local-dev/private/login.txt (0600).')
