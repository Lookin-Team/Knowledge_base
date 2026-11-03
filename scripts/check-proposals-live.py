#!/usr/bin/env python3
"""Read-only HTTPS checks of proposal access. No credentials or content in output."""
import http.cookiejar
import html
import json
from pathlib import Path
import re
import urllib.request
import urllib.parse
import urllib.error

ROOT=Path(__file__).resolve().parent.parent
BASE='https://base.lookin.team'

def fetch(client,path,data=None):
    try:
        with client.open(urllib.request.Request(BASE+path,data=data,headers={'Accept':'application/json'}),timeout=25) as r:
            return r.status,r.read(),r.url
    except urllib.error.HTTPError as e:
        return e.code,e.read(),e.url

def check(email,password,moderator):
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    code,body,_=fetch(client,'/login');assert code==200
    token=html.unescape(re.search(r'name="_token"\s+value="([^"]+)"',body.decode()).group(1))
    code,body,url=fetch(client,'/login',urllib.parse.urlencode({'_token':token,'email':email,'password':password}).encode())
    assert urllib.parse.urlsplit(url).path!='/login','Login failed; credentials withheld'
    code,body,_=fetch(client,'/publication-proposals/new');assert code==200
    assert b'multipart/form-data' in body and b'name="files[]"' in body
    code,body,_=fetch(client,'/publication-proposals');assert code==200
    assert ('Запросы на публикацию'.encode() in body)==moderator
    if moderator:
        code,body,_=fetch(client,'/publication-proposals?queue=1');assert code==200
    else:
        # A direct queue parameter must still display only this user's list.
        code,body,_=fetch(client,'/publication-proposals?queue=1');assert code==200
        assert 'Запросы на публикацию'.encode() not in body
        code,_,_=fetch(client,'/create-book');assert code==403
        code,_,_=fetch(client,'/settings/users');assert code==403
    code,_,_=fetch(client,'/publication-proposals',b'title=csrf-check');assert code==419
    code,body,_=fetch(client,'/')
    token=html.unescape(re.search(r'name="_token"\s+value="([^"]+)"',body.decode()).group(1))
    fetch(client,'/logout',urllib.parse.urlencode({'_token':token}).encode())
    return {'form_files_and_personal_list':'PASS','queue_access':'PASS','csrf':'PASS','roles_unchanged_checks':'PASS'}

def main():
    access=ROOT.parent/'.server-access'
    state=json.loads((access/'deployment/state.json').read_text())
    report={'admin':check(state['admin_email'],state['admin_password'],True),'colleagues':[]}
    for person in json.loads((access/'colleagues/pilot-20261030.json').read_text())['people']:
        try:
            report['colleagues'].append(check(person['email'],person['password'],False))
        except AssertionError as error:
            if str(error) != 'Login failed; credentials withheld':
                raise
            report['colleagues'].append({'login':'NOT VERIFIED: saved initial password no longer accepted'})
    report['https']='PASS (certificate verification enabled)'
    (ROOT/'local-dev/proposals-live-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
