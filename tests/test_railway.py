"""Deployment boundaries for the low-budget pilot, without weakening public SaaS auth."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.config import Settings
from backend.app import create_app
from backend.store import Store
from backend.auth import Identity
from scripts.railway_start import provision_pilot


class RailwayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.cfg=Settings(production=True,launch_mode='private-pilot',origin='https://flavo.example',database=str(Path(self.temp.name)/'pilot.sqlite3'),run_worker=False,railway=True,stripe_key='',stripe_webhook='',prices={'starter':'','team':''},smtp_host='',mail_from='')

    def tearDown(self):
        self.temp.cleanup()

    def test_pilot_closes_registration_demo_and_unauthenticated_analysis(self):
        with TestClient(create_app(self.cfg),base_url=self.cfg.origin,headers={'Origin':self.cfg.origin}) as client:
            self.assertFalse(client.get('/api/session').json()['signupAvailable'])
            self.assertFalse(client.get('/api/session').json()['demoAvailable'])
            self.assertEqual(client.post('/api/auth/register',json={}).status_code,403)
            self.assertEqual(client.post('/api/auth/demo',json={}).status_code,404)
            self.assertEqual(client.post('/api/jobs',json={}).status_code,401)
            self.assertEqual(client.get('/api/reports').status_code,401)
            self.assertEqual(client.post('/api/auth/email',json={}).status_code,503)

    def test_pilot_provisioning_persists_credentials_and_requires_password_on_first_boot(self):
        with patch.dict('os.environ',{'FLAVO_PILOT_EMAIL':'','FLAVO_PILOT_PASSWORD':''}):
            with self.assertRaisesRegex(RuntimeError,'First private-pilot boot'):provision_pilot(self.cfg)
        with patch.dict('os.environ',{'FLAVO_PILOT_EMAIL':'owner@example.test','FLAVO_PILOT_PASSWORD':'disposable-test-password'}):provision_pilot(self.cfg)
        store=Store(self.cfg.database);auth=Identity(store,self.cfg)
        account=auth.login('owner@example.test','disposable-test-password')
        with patch.dict('os.environ',{'FLAVO_PILOT_EMAIL':'other@example.test','FLAVO_PILOT_PASSWORD':'do-not-overwrite-this-password'}):provision_pilot(self.cfg)
        self.assertEqual(account,auth.login('owner@example.test','disposable-test-password'))
        self.assertEqual(store.one('SELECT COUNT(*) n FROM users')['n'],1)
        self.assertEqual(store.entitlement(account['workspace'])['remaining'],5)
        with TestClient(create_app(self.cfg),base_url=self.cfg.origin,headers={'Origin':self.cfg.origin}) as client:
            response=client.post('/api/auth/login',json={'email':'owner@example.test','password':'disposable-test-password'})
            self.assertEqual(response.status_code,200)
            self.assertIn('Secure',response.headers['set-cookie']);self.assertIn('HttpOnly',response.headers['set-cookie'])
            self.assertEqual(client.post('/api/jobs',json={}).status_code,403) # CSRF still enforced.

    def test_healthcheck_host_is_limited_to_get_health_on_railway(self):
        with TestClient(create_app(self.cfg),base_url=self.cfg.origin) as client:
            self.assertEqual(client.get('/api/health',headers={'Host':'healthcheck.railway.app'}).status_code,200)
            self.assertEqual(client.get('/api/session',headers={'Host':'healthcheck.railway.app'}).status_code,403)
            self.assertEqual(client.post('/api/health',headers={'Host':'healthcheck.railway.app'}).status_code,403)
        self.cfg.railway=False
        with TestClient(create_app(self.cfg),base_url=self.cfg.origin) as client:
            self.assertEqual(client.get('/api/health',headers={'Host':'healthcheck.railway.app'}).status_code,403)

    def test_saas_mode_still_requires_real_configuration_and_pilot_rejects_billing(self):
        self.cfg.validate()
        self.cfg.stripe_key='sk_test_placeholder'
        with self.assertRaisesRegex(RuntimeError,'Private pilot'):self.cfg.validate()
        self.cfg.stripe_key='';self.cfg.launch_mode='saas'
        with self.assertRaisesRegex(RuntimeError,'SMTP'):self.cfg.validate()
        self.cfg.launch_mode='unknown'
        with self.assertRaisesRegex(RuntimeError,'FLAVO_LAUNCH_MODE'):self.cfg.validate()
