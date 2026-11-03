"""Local-only HTTP check; uses existing protected synthetic login. Prints no secrets."""
import runpy
import urllib.request
import urllib.error
import json
from pathlib import Path
ctx = runpy.run_path(str(Path(__file__).with_name('check-http.py')))
opener, base = ctx['opener'], ctx['base']
result = {}
for path in ['/publication-proposals/new', '/publication-proposals', '/publication-proposals?queue=1']:
    with opener.open(base + path, timeout=15) as response:
        html=response.read().decode()
        assert response.status == 200 and 'Предложить публикацию' in html
        result[path]='PASS'
try:
    opener.open(urllib.request.Request(base+'/publication-proposals',data=b'title=test'),timeout=15)
    raise AssertionError('CSRF accepted')
except urllib.error.HTTPError as error:
    assert error.code == 419, error.code
    result['csrf_missing_token']='PASS (419)'
print(json.dumps(result, ensure_ascii=False, indent=2))
