"""Local login smoke test. Never prints credentials or cookies."""
from pathlib import Path
import http.cookiejar
import json
import re
import urllib.parse
import urllib.request

root = Path(__file__).resolve().parent.parent
base = 'http://127.0.0.1:8080'
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.ProxyHandler({}))
with opener.open(base + '/login', timeout=15) as response:
    assert response.status == 200
    page = response.read().decode()
token = re.search(r'name="_token"\s+value="([^"]+)"', page)
assert token, 'Login form CSRF token not found'
credentials = json.loads((root / 'local-dev/private/admin.json').read_text())
data = urllib.parse.urlencode({'_token': token.group(1), 'email': credentials['email'], 'password': credentials['password']}).encode()
request = urllib.request.Request(base + '/login', data=data, headers={'Referer': base + '/login', 'Origin': base})
with opener.open(request, timeout=15) as response:
    response.read()
    final_path = urllib.parse.urlparse(response.url).path
    assert response.status == 200 and final_path != '/login', f'Login did not succeed: {final_path}'
print(json.dumps({'login_page_status': 200, 'synthetic_admin_login': 'PASS', 'after_login_path': final_path}, indent=2))
