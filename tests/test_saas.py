"""Public SaaS boundaries, billing synchronization and durable agent execution.

All databases are disposable, and Stripe/model/email calls are stubbed.
The evidence tool runs the real shipped Node engine against the actual snapshot.
"""
import asyncio
import copy
import hashlib
import hmac
import json
import ssl
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.agent import Runner, canonical, validate_run
from backend.config import Settings
from backend.lease import WorkerLease
from backend.store import Problem, Store
from backend.auth import COOKIE

PROFILE = {'company':'Evidence Foods','product':'kimchi','market':'일본',
           'format':'냉장 완제품','channel':'온라인 직접 판매','goal':'Small export pilot','language':'en'}
INPUT = {'kind':'report','input':{'profile':PROFILE,'mode':'evidence'}}
PASSWORD = 'only-a-disposable-test-password'


class SaaSTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cfg = Settings(database=str(Path(self.temp.name)/'test.sqlite3'), run_worker=False,
                            stripe_key='', stripe_webhook='', prices={'starter':'','team':''}, smtp_host='')
        self.app = create_app(self.cfg)
        self.store = self.app.state.store
        self.auth = self.app.state.auth
        self.billing = self.app.state.billing
        self.clients = []

    def tearDown(self):
        for client in self.clients: client.close()
        self.temp.cleanup()

    def client(self, address=None):
        c = TestClient(self.app, headers={'Origin':'http://testserver'})
        self.clients.append(c)
        if address:
            response = c.post('/api/auth/register', json={'name':address.split('@')[0], 'company':address,
                                                         'email':address,'password':PASSWORD})
            self.assertEqual(response.status_code,200,response.text)
            session = c.get('/api/session').json()
            c.headers['X-CSRF-Token'] = session['csrf']
            c.identity = {'user':session['user']['id'],'workspace':session['workspace']['id'],'email':address}
        return c

    def enqueue(self, c, key='test-idempotency-0001', payload=None):
        r = c.post('/api/jobs',json=payload or INPUT,headers={'Idempotency-Key':key})
        self.assertEqual(r.status_code,202,r.text)
        return r.json()

    def paid(self, c, plan='starter'):
        self.store.execute("UPDATE workspaces SET plan=?,billing_status='active',period_end=? WHERE id=?",
                           (plan,time.time()+86400,c.identity['workspace']))

    def signature(self, event, timestamp=None):
        raw = json.dumps(event,separators=(',',':')).encode()
        timestamp = int(time.time()) if timestamp is None else timestamp
        signature = hmac.new(self.cfg.stripe_webhook.encode(),str(timestamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return raw, f't={timestamp},v1={signature}'

    def stripe(self, c):
        self.cfg.stripe_key='sk_test_fake';self.cfg.stripe_webhook='whsec_fake'
        self.cfg.prices={'starter':'price_starter','team':'price_team'}
        self.store.execute('UPDATE workspaces SET customer=? WHERE id=?',('cus_test',c.identity['workspace']))
        return {'id':'sub_test','customer':'cus_test','status':'active','metadata':{'workspace':c.identity['workspace']},
                'items':{'data':[{'price':{'id':'price_starter'},'quantity':1,'current_period_start':time.time(),
                                  'current_period_end':time.time()+86400}]}}

    def test_authentication_csrf_origin_and_no_legacy_api(self):
        c=self.client()
        for path in ['/api/jobs','/api/reports','/api/workspace','/api/questions','/api/status']:
            self.assertEqual(c.get(path).status_code,401)
        c=self.client('one@example.test')
        cookie=c.cookies.get(COOKIE)
        self.assertGreater(len(cookie),30)
        self.assertNotIn(cookie,str(self.store.all('SELECT * FROM sessions')))
        headers={'Idempotency-Key':'boundary-test-1234','X-CSRF-Token':'bad'}
        self.assertEqual(c.post('/api/jobs',json=INPUT,headers=headers).status_code,403)
        self.assertEqual(c.post('/api/jobs',json=INPUT,headers={**headers,'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(c.post('/api/report',json={'evidence':['fake']}).status_code,404)
        self.assertEqual(c.get('/var/flavo.sqlite3').status_code,404)
        self.assertIn("script-src 'self'",c.get('/').headers['content-security-policy'])
        self.assertEqual(c.get('/api/session').headers['cache-control'],'no-store')

    def test_tenant_isolation_for_jobs_reports_review_and_switch(self):
        a,b=self.client('a@example.test'),self.client('b@example.test')
        job=self.enqueue(a);claimed=self.store.claim();self.store.finish(claimed,result={'profile':PROFILE,'language':'en'})
        self.assertEqual(len(a.get('/api/reports').json()['reports']),1)
        self.assertEqual(b.get('/api/reports').json()['reports'],[])
        self.assertEqual(b.get('/api/jobs').json()['jobs'],[])
        for path in [f"/api/jobs/{job['id']}",f"/api/jobs/{job['id']}/cancel",f"/api/jobs/{job['id']}/retry",f"/api/reports/{job['id']}/review"]:
            response=b.get(path) if path.endswith(job['id']) else b.post(path,json={})
            self.assertEqual(response.status_code,404,response.text)
        self.assertEqual(b.post('/api/workspaces/switch',json={'workspace':a.identity['workspace']}).status_code,404)
        self.assertEqual(a.post(f"/api/reports/{job['id']}/review",json={}).status_code,200)
        self.assertIsNotNone(a.get('/api/reports').json()['reports'][0]['reviewedAt'])

    def test_input_authority_body_limit_and_invalid_types(self):
        c=self.client('one@example.test');payload=copy.deepcopy(INPUT)
        payload.update(workspace='someone-else',model='attacker');payload['input']['evidence']=[{'id':'E1','text':'invented'}]
        job=self.enqueue(c,payload=payload)
        saved=self.store.one('SELECT * FROM jobs WHERE id=?',(job['id'],))
        self.assertEqual(saved['workspace'],c.identity['workspace'])
        self.assertNotIn('invented',saved['payload']);self.assertNotIn('attacker',saved['payload'])
        for value in [None,[],7,'invalid']:
            self.assertEqual(c.post('/api/jobs',json={'kind':'report','input':value},headers={'Idempotency-Key':'bad-input-1234567'}).status_code,422)
        self.assertEqual(c.post('/api/jobs',json={'oversized':'x'*61000}).status_code,413)
        self.assertEqual(c.post('/api/jobs',content='{}',headers={'Content-Type':'text/plain'}).status_code,415)

    def test_idempotency_quota_failure_refunds_and_durable_recovery(self):
        c=self.client('one@example.test');job=self.enqueue(c)
        self.assertEqual(job['id'],self.enqueue(c)['id'])
        changed=copy.deepcopy(INPUT);changed['input']['profile']['company']='Changed'
        self.assertEqual(c.post('/api/jobs',json=changed,headers={'Idempotency-Key':'test-idempotency-0001'}).status_code,409)
        self.assertEqual(self.store.entitlement(c.identity['workspace'])['used'],1)
        claimed=self.store.claim();self.store.finish(claimed,error='generation_failed')
        self.assertEqual(self.store.entitlement(c.identity['workspace'])['used'],0)
        for i in range(5):
            self.enqueue(c,f'quota-key-{i:012d}');claimed=self.store.claim();self.store.finish(claimed,result={'profile':PROFILE})
        self.assertEqual(c.post('/api/jobs',json=INPUT,headers={'Idempotency-Key':'quota-final-12345678'}).status_code,402)
        reopened=Store(self.cfg.database)
        self.assertEqual(len(reopened.reports(c.identity['workspace'])),5)
        self.assertEqual(reopened.entitlement(c.identity['workspace'])['remaining'],0)

    def test_atomic_reservation_does_not_oversubscribe(self):
        c=self.client('one@example.test')
        for i in range(4):
            self.store.enqueue(c.identity,'report',INPUT['input'],f'finished-{i}');self.store.finish(self.store.claim(),result={})
        def request(i):
            try:return self.store.enqueue(c.identity,'report',INPUT['input'],f'concurrent-{i}')['id']
            except Problem as e:return e.status
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(request,range(6)))
        self.assertEqual(sum(isinstance(r,str) for r in results),1)
        self.assertEqual(results.count(402),5)

    def test_cancel_wins_over_completion_and_restart_is_visible(self):
        c=self.client('one@example.test');j=self.enqueue(c);claimed=self.store.claim()
        self.store.cancel(c.identity,j['id']);self.store.finish(claimed,result={'profile':PROFILE})
        self.assertEqual(self.store.job(c.identity['workspace'],j['id'])['status'],'cancelled')
        self.assertEqual(self.store.reports(c.identity['workspace']),[])
        self.assertEqual(self.store.entitlement(c.identity['workspace'])['used'],0)
        j=self.enqueue(c,'restart-key-1234567');self.store.claim();self.store.recover()
        result=self.store.job(c.identity['workspace'],j['id'])
        self.assertEqual(result['error'],'worker_restarted')
        retry=c.post(f"/api/jobs/{j['id']}/retry",json={},headers={'Idempotency-Key':'new-retry-12345678'})
        self.assertEqual(retry.status_code,200)
        self.assertNotEqual(retry.json()['id'],j['id'])

    def test_reset_token_one_time_and_revokes_existing_sessions(self):
        c=self.client('one@example.test');token=self.auth.token('reset',c.identity)
        response=c.post('/api/auth/reset',json={'token':token,'password':PASSWORD+'new'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(c.get('/api/session').json()['authenticated'])
        self.assertEqual(c.post('/api/auth/reset',json={'token':token,'password':PASSWORD}).status_code,400)
        self.assertEqual(c.post('/api/auth/login',json={'email':c.identity['email'],'password':PASSWORD}).status_code,401)
        self.assertEqual(c.post('/api/auth/login',json={'email':c.identity['email'],'password':PASSWORD+'new'}).status_code,200)

    def test_invitation_identity_seats_roles_and_revocation(self):
        a,b=self.client('owner@example.test'),self.client('member@example.test');self.paid(a)
        token=self.auth.token('invite',{'workspace':a.identity['workspace'],'email':b.identity['email']})
        self.assertEqual(a.post('/api/workspace/accept',json={'token':token}).status_code,403)
        self.assertEqual(b.post('/api/workspace/accept',json={'token':token}).status_code,200)
        self.assertEqual(b.get('/api/session').json()['workspace']['role'],'member')
        for path in ['/api/billing/checkout','/api/billing/portal','/api/workspace/invite','/api/workspace/remove-member']:
            self.assertEqual(b.post(path,json={'email':'x@example.test','plan':'team'}).status_code,403)
        response=a.post('/api/workspace/remove-member',json={'email':b.identity['email']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(b.get('/api/reports').status_code,401)
        self.assertEqual(a.post('/api/workspace/remove-member',json={'email':a.identity['email']}).status_code,409)

    def test_trial_expiration_and_seat_downgrade_stop_new_runs(self):
        a,b=self.client('a@example.test'),self.client('b@example.test')
        self.store.execute('UPDATE workspaces SET trial_end=? WHERE id=?',(time.time()-1,a.identity['workspace']))
        self.assertEqual(a.post('/api/jobs',json=INPUT,headers={'Idempotency-Key':'expired-trial-key'}).status_code,402)
        self.store.execute('UPDATE workspaces SET trial_end=? WHERE id=?',(time.time()+100,a.identity['workspace']))
        self.store.execute("INSERT INTO members VALUES(?,?,'member')",(a.identity['workspace'],b.identity['user']))
        self.assertTrue(a.get('/api/session').json()['usage']['overSeatLimit'])
        self.assertEqual(a.post('/api/jobs',json=INPUT,headers={'Idempotency-Key':'overseats-test-key'}).status_code,402)

    def test_production_disables_demo_and_requires_deployment_configuration(self):
        self.cfg.production=True
        with self.assertRaises(RuntimeError):self.cfg.validate()
        self.cfg.origin='https://flavo.example'
        with self.assertRaises(RuntimeError):self.cfg.validate()
        self.cfg.production=False;c=self.client();self.assertEqual(c.post('/api/auth/demo',json={}).status_code,200)
        cookie=c.cookies.get(COOKIE)
        self.cfg.production=True
        c.base_url='https://flavo.example';c.headers['Origin']='https://flavo.example'
        self.assertEqual(c.post('/api/auth/demo',json={}).status_code,404)
        self.assertFalse(c.get('/api/session',headers={'Cookie':COOKIE+'='+cookie}).json()['authenticated'])

    def test_verification_required_and_email_link_is_one_time(self):
        c=self.client('one@example.test');self.store.execute('UPDATE users SET verified=0 WHERE id=?',(c.identity['user'],))
        self.assertEqual(c.post('/api/auth/login',json={'email':c.identity['email'],'password':PASSWORD}).status_code,403)
        token=self.auth.token('verify',c.identity)
        self.assertEqual(c.post('/api/auth/verify',json={'token':token}).status_code,200)
        self.assertEqual(c.post('/api/auth/verify',json={'token':token}).status_code,400)

    def test_mail_verifies_tls_peer_before_login_and_delivery(self):
        self.cfg.smtp_host='mail.example.test';self.cfg.mail_from='hello@example.test'
        self.cfg.smtp_user='test-user';self.cfg.smtp_password='disposable-password'
        with patch('backend.auth.smtplib.SMTP') as smtp:
            connection=smtp.return_value.__enter__.return_value
            self.auth.mail('customer@example.test','verify','disposable-token')
            context=connection.starttls.call_args.kwargs['context']
            self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertEqual([c[0] for c in connection.mock_calls],['starttls','login','send_message'])
        with patch('backend.auth.smtplib.SMTP') as smtp:
            connection=smtp.return_value.__enter__.return_value
            connection.starttls.side_effect=ssl.SSLCertVerificationError('untrusted peer')
            with self.assertRaises(Problem):self.auth.mail('customer@example.test','verify','disposable-token')
            connection.login.assert_not_called();connection.send_message.assert_not_called()

    def test_production_session_headers_and_verified_signup(self):
        self.cfg.production=True;self.cfg.origin='https://flavo.example'
        self.cfg.smtp_host='mail.example.test';self.cfg.mail_from='hello@example.test'
        c=TestClient(self.app,base_url=self.cfg.origin,headers={'Origin':self.cfg.origin})
        self.clients.append(c)
        with patch.object(self.auth,'mail') as mail:
            r=c.post('/api/auth/register',json={'name':'Production Test','company':'Production Test',
                                              'email':'production@example.test','password':PASSWORD})
        self.assertTrue(r.json()['verificationRequired'])
        self.assertFalse(c.get('/api/session').json()['authenticated'])
        token=mail.call_args.args[2]
        r=c.post('/api/auth/verify',json={'token':token})
        self.assertEqual(r.status_code,200,r.text)
        cookie=r.headers['set-cookie'].lower()
        for flag in ['secure','httponly','samesite=strict']:self.assertIn(flag,cookie)
        self.assertIn('max-age=',r.headers['strict-transport-security'])
        self.assertEqual(c.get('/api/reports').status_code,200)
        self.assertEqual(c.post('/api/jobs',json=INPUT).status_code,403)

    def test_backup_restores_tenant_data_and_refuses_overwrite(self):
        c=self.client('backup@example.test');job=self.enqueue(c)
        self.store.finish(self.store.claim(),result={'profile':PROFILE,'summary':'Recovery fixture'})
        destination=Path(self.temp.name)/'restored'/'flavo.sqlite3'
        import os
        env={**os.environ,'FLAVO_DATABASE':self.cfg.database}
        command=[sys.executable,'scripts/backup.py',str(destination)]
        result=subprocess.run(command,env=env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        restored=Store(destination)
        self.assertEqual(restored.reports(c.identity['workspace'])[0]['summary'],'Recovery fixture')
        self.assertEqual(restored.job(c.identity['workspace'],job['id'])['status'],'completed')
        with closing(sqlite3.connect(destination)) as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertNotEqual(subprocess.run(command,env=env,capture_output=True).returncode,0)
        self.assertEqual(restored.reports(c.identity['workspace'])[0]['summary'],'Recovery fixture')

    def test_stripe_signatures_duplicate_delayed_and_cancelled_events(self):
        c=self.client('one@example.test');current=self.stripe(c)
        event={'id':'evt_1','type':'customer.subscription.updated','data':{'object':{'id':'sub_test','status':'active'}}}
        raw,sig=self.signature(event)
        with patch.object(self.billing,'request',return_value=current) as fetch:
            self.assertEqual(self.billing.webhook(raw,sig),{'received':True})
            self.billing.webhook(raw,sig);self.assertEqual(fetch.call_count,1)
        self.assertEqual(self.store.entitlement(c.identity['workspace'])['plan'],'starter')
        self.assertTrue(self.store.entitlement(c.identity['workspace'])['active'])
        current['status']='canceled';event['id']='evt_delayed';raw,sig=self.signature(event)
        with patch.object(self.billing,'request',return_value=current):self.billing.webhook(raw,sig)
        self.assertFalse(self.store.entitlement(c.identity['workspace'])['active'])
        for body,signature in [(raw,sig+'bad'),self.signature(event,int(time.time())-600),(raw+b' ',sig)]:
            with self.assertRaises(Problem):self.billing.webhook(body,signature)

    def test_stripe_cannot_upgrade_a_different_customer_or_unknown_price(self):
        c=self.client('one@example.test');current=self.stripe(c)
        current['customer']='cus_wrong';event={'id':'evt_wrong','type':'customer.subscription.created','data':{'object':{'id':'sub_test'}}}
        raw,sig=self.signature(event)
        with patch.object(self.billing,'request',return_value=current):self.billing.webhook(raw,sig)
        self.assertEqual(self.store.entitlement(c.identity['workspace'])['plan'],'trial')
        current['customer']='cus_test';current['items']['data'][0]['price']['id']='price_unsupported';event['id']='evt_unknown';raw,sig=self.signature(event)
        with patch.object(self.billing,'request',return_value=current):self.billing.webhook(raw,sig)
        self.assertFalse(self.store.entitlement(c.identity['workspace'])['active'])

    def test_checkout_has_server_price_and_stable_retry_parameters(self):
        c=self.client('one@example.test');self.stripe(c)
        calls=[]
        def fake_request(method,path,data=None,key=None):
            if path=='subscriptions':return {'data':[],'has_more':False}
            calls.append((path,data,key))
            if len(calls)==1:raise Problem(503,'unknown','Unknown','Unknown')
            return {'id':'cs_test','url':'https://checkout.stripe.com/c/pay/test','expires_at':float(data['expires_at'])}
        with patch('backend.billing.time.time',return_value=1800000001),patch.object(self.billing,'request',side_effect=fake_request):
            with self.assertRaises(Problem):self.billing.checkout(c.identity,'starter')
            self.billing.checkout(c.identity,'starter')
        self.assertEqual(calls[0],calls[1])
        self.assertEqual(calls[0][1]['line_items[0][price]'],'price_starter')
        self.assertEqual(calls[0][1]['customer'],'cus_test')
        self.assertEqual(self.store.entitlement(c.identity['workspace'])['plan'],'trial')

    def test_checkout_waits_for_a_paid_subscription_even_before_webhook(self):
        c=self.client('one@example.test');self.stripe(c)
        with patch.object(self.billing,'request',return_value={'data':[{'status':'active'}],'has_more':False}) as request:
            with self.assertRaises(Problem) as error:self.billing.checkout(c.identity,'starter')
        self.assertEqual(error.exception.code,'existing_subscription')
        self.assertEqual(request.call_count,1)

    def test_malformed_checkout_plan_is_rejected_before_stripe(self):
        c=self.client('one@example.test');self.stripe(c)
        with patch.object(self.billing,'request') as request:
            for plan in [[],{},42,None,'unknown']:
                response=c.post('/api/billing/checkout',json={'plan':plan})
                self.assertEqual(response.status_code,422,response.text)
            request.assert_not_called()

    def test_single_worker_lock_releases_on_shutdown(self):
        with WorkerLease(self.cfg.database):
            with self.assertRaises(RuntimeError):
                with WorkerLease(self.cfg.database):pass
        with WorkerLease(self.cfg.database):pass

    def test_real_evidence_report_is_persisted_with_provenance(self):
        c=self.client('one@example.test');job=self.enqueue(c);runner=Runner(self.store,self.cfg)
        asyncio.run(runner.run_one(self.store.claim()))
        result=self.store.job(c.identity['workspace'],job['id'])
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(result['result']['provenance']['evidenceAuthority'],'server')
        self.assertEqual(result['result']['profile']['company'],PROFILE['company'])
        self.assertEqual(result['result']['id'],job['id'])
        receipt=result['result']['provenance']
        self.assertEqual(receipt['runId'],job['id'])
        self.assertEqual(receipt['linkedItemCount'],3)
        self.assertEqual(receipt['evidenceCount'],8)
        self.assertFalse(receipt['generatedByAI'])
        self.assertNotIn('drafting',[e['stage'] for e in result['events']])
        self.assertEqual(len(self.store.reports(c.identity['workspace'])),1)
        context=asyncio.run(canonical('context',PROFILE))
        self.assertEqual(len(context['evidence']),8)
        review='/api/reports/'+job['id']+'/review'
        self.assertEqual(c.post(review,json={}).status_code,200)
        report=c.get('/api/reports').json()['reports'][0]
        self.assertEqual(report['reviewedBy'],'one')
        self.assertEqual(c.post(review,json={}).status_code,200)
        self.assertEqual(c.get('/api/reports').json()['reports'][0]['reviewedAt'],report['reviewedAt'])
        self.assertEqual(len(self.store.all("SELECT * FROM audit WHERE action='report.reviewed'")),1)

    def test_model_failure_falls_back_to_observed_facts_without_charging(self):
        class FailingModel:
            async def generate(self,*args):raise RuntimeError('model_unavailable')
        c=self.client('one@example.test');kind,payload=validate_run({'kind':'ask','input':{'question':'How many kimchi reviews mention spiciness?','language':'en'}})
        job=self.store.enqueue(c.identity,kind,payload,'qa-fallback-test');runner=Runner(self.store,self.cfg,FailingModel())
        asyncio.run(runner.run_one(self.store.claim()))
        result=self.store.job(c.identity['workspace'],job['id'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['result']['mode'],'data')
        self.assertFalse(result['result']['provenance']['generatedByAI'])
        self.assertIn('195',str(result['result']['evidence']))
        self.assertEqual(self.store.entitlement(c.identity['workspace'])['used'],0)
        self.assertEqual(len(c.get('/api/questions').json()['turns']),1)

    def test_running_cancel_interrupts_model_and_never_saves_report(self):
        class SlowModel:
            cancelled=False
            async def generate(self,*args):
                try:await asyncio.sleep(30)
                except asyncio.CancelledError:self.cancelled=True;raise
        c=self.client('one@example.test');model=SlowModel()
        payload={'profile':PROFILE,'mode':'ai'};job=self.store.enqueue(c.identity,'report',payload,'slow-cancel-test')
        runner=Runner(self.store,self.cfg,model)
        async def scenario():
            task=asyncio.create_task(runner.run_one(self.store.claim()))
            for _ in range(100):
                if self.store.job(c.identity['workspace'],job['id'])['stage']=='drafting':break
                await asyncio.sleep(.05)
            self.store.cancel(c.identity,job['id']);await task
        asyncio.run(scenario())
        self.assertTrue(model.cancelled)
        self.assertEqual(self.store.job(c.identity['workspace'],job['id'])['status'],'cancelled')
        self.assertEqual(self.store.reports(c.identity['workspace']),[])


if __name__=='__main__':unittest.main()
