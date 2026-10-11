"""CI-only production-container smoke check; no external email, payments or inference.

Run inside a disposable container with the CI placeholder configuration.
The HTTP connection uses loopback; the Host header matches its configured origin.
"""
import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
origin=os.environ['FLAVO_PUBLIC_URL'].rstrip('/')
host=urlparse(origin).netloc
parser=argparse.ArgumentParser()
parser.add_argument('--port',type=int,default=4175)
port=parser.parse_args().port

def request(path,expected=200,data=None,extra=None):
    headers={'Host':host,**(extra or {})}
    if data is not None:headers['Content-Type']='application/json'
    req=Request(f'http://127.0.0.1:{port}'+path,headers=headers,
                data=None if data is None else json.dumps(data).encode())
    try:response=urlopen(req,timeout=10)
    except HTTPError as error:response=error
    with response:
        body=response.read()
        assert response.code==expected,(path,response.code,expected)
        return body,response.headers

health,headers=request('/api/health')
assert json.loads(health)['status']=='ok'
assert headers['Cache-Control']=='no-store'
assert 'max-age=' in headers['Strict-Transport-Security']
assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
session,_=request('/api/session')
assert json.loads(session)=={
    'authenticated':False,'demoAvailable':False,
    'signupAvailable':True,'launchMode':'saas',
}
request('/api/reports',401)
request('/api/jobs',401)
request('/api/auth/demo',404,data={},extra={'Origin':origin})
request('/api/auth/login',403,data={},extra={'Origin':'https://foreign.example'})
request('/var/flavo.sqlite3',404)
request('/data/FlavorSense.csv',404)
page,_=request('/')
assert b'./src/app.mjs' in page
for path in ['/src/app.mjs','/src/studio.css','/src/method.mjs','/src/9.png',
             '/src/shutterstock_1867661479.jpg','/src/generated/data.json','/src/geo/world.json']:
    request(path)
from backend.agent import canonical
profile={'company':'CI fixture','product':'kimchi','market':'일본','format':'냉장 완제품',
         'channel':'온라인 직접 판매','goal':'CI validation','language':'en'}
report=asyncio.run(canonical('report',profile))
assert len(report['evidence'])==8
assert report['analysis']['food']['reviewCount']==195
assert len(report['localization'])==3
print('Production container smoke checks passed: health, auth boundary, static assets, Node evidence tools.')
