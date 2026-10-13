import test from 'node:test';
import assert from 'node:assert/strict';
import {serviceOrigin,serviceLink,publicServiceLink,serviceEntry} from '../src/portal.mjs';
import {startupEntry,entryHash} from '../src/entry.mjs';

test('public workspace links use an HTTPS origin and a bounded feature intent',()=>{
  for(const bad of ['javascript:alert(1)','http://app.example','https://user:secret@app.example','https://app.example/path','https://app.example/?key=x','https://app.example/#x','https://127.0.0.1','https://localhost','https://10.1.2.3','https://jellyfish040918.github.io'])assert.equal(serviceOrigin(bad),'',bad);
  const url=new URL(serviceLink('https://flavo.up.railway.app/','new-report','en'));
  assert.equal(url.origin,'https://flavo.up.railway.app');assert.equal(url.searchParams.get('start'),'new-report');assert.equal(url.hash,'#reports');
  assert.equal(serviceLink(url.origin,'https://evil.example'),'');
  assert.equal(serviceLink('', 'ask'),'');
});
test('post-login intent preserves the requested feature without open redirects',()=>{
  assert.deepEqual(startupEntry('?start=new-report&lang=en'),{view:'new-report',language:'en'});
  assert.equal(entryHash(startupEntry('?start=ask').view),'#ask');
  assert.equal(entryHash(startupEntry('?start=new-report').view),'#reports');
  assert.deepEqual(startupEntry('?start=https://evil.example&lang=<script>'),{view:'',language:''});
  assert.equal(entryHash('register'),'#dashboard');
});
test('unconnected entry offers no pretend chat form and only labels actual service links',()=>{
  const pending=serviceEntry('ask',{appUrl:''});
  assert.match(pending,/클라우드 서비스 연결 대기/);assert.doesNotMatch(pending,/<form|<textarea/);
  const connected=serviceEntry('ask',{appUrl:'https://flavo.up.railway.app'});
  assert.match(connected,/https:\/\/flavo.up.railway.app/);assert.doesNotMatch(connected,/127\.0\.0\.1/);
});
test('pilot entry sends registration CTAs to sign-in without losing language or research intent',()=>{
  const pilot={appUrl:'https://flavo.up.railway.app',launchMode:'private-pilot'};
  const signup=new URL(publicServiceLink(pilot,'register','en'));
  assert.equal(signup.hash,'#login');assert.equal(signup.searchParams.get('lang'),'en');
  assert.equal(new URL(publicServiceLink(pilot,'new-report')).searchParams.get('start'),'new-report');
  assert.match(serviceEntry('register',pilot),/발급받은 파일럿 계정/);
  assert.doesNotMatch(serviceEntry('register',pilot),/이메일 인증으로 계정 생성/);
  assert.equal(new URL(publicServiceLink({...pilot,launchMode:'saas'},'register')).hash,'#register');
});
