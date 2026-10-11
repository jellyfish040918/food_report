import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)

@dataclass
class Settings:
    production: bool = field(default_factory=lambda: os.getenv('FLAVO_ENV') == 'production')
    origin: str = field(default_factory=lambda: os.getenv('FLAVO_PUBLIC_URL', 'http://127.0.0.1:4175').rstrip('/'))
    database: str = field(default_factory=lambda: os.getenv('FLAVO_DATABASE', str(ROOT / 'var/flavo.sqlite3')))
    model: str = field(default_factory=lambda: os.getenv('FLAVO_MODEL', 'qwen3.5:9b'))
    ollama: str = field(default_factory=lambda: os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434').rstrip('/'))
    stripe_key: str = field(default_factory=lambda: os.getenv('STRIPE_SECRET_KEY', ''))
    stripe_webhook: str = field(default_factory=lambda: os.getenv('STRIPE_WEBHOOK_SECRET', ''))
    prices: dict = field(default_factory=lambda: {'starter':os.getenv('STRIPE_PRICE_STARTER',''),'team':os.getenv('STRIPE_PRICE_TEAM','')})
    smtp_host: str = field(default_factory=lambda: os.getenv('SMTP_HOST',''))
    smtp_port: int = field(default_factory=lambda: int(os.getenv('SMTP_PORT','587')))
    smtp_user: str = field(default_factory=lambda: os.getenv('SMTP_USER',''))
    smtp_password: str = field(default_factory=lambda: os.getenv('SMTP_PASSWORD',''))
    mail_from: str = field(default_factory=lambda: os.getenv('MAIL_FROM',''))
    run_worker: bool = True

    def validate(self):
        url=urlparse(self.origin)
        if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.path not in ('','/') or url.query or url.fragment:
            raise RuntimeError('FLAVO_PUBLIC_URL must be an origin without credentials or path.')
        if self.production and url.scheme!='https':
            raise RuntimeError('Production requires an HTTPS FLAVO_PUBLIC_URL.')
        if self.production and (not self.smtp_host or not self.mail_from):
            raise RuntimeError('Production signup requires SMTP_HOST and MAIL_FROM for verification and recovery.')
        if self.production and not all([self.stripe_key,self.stripe_webhook,*self.prices.values()]):
            raise RuntimeError('Production subscriptions require Stripe secret, webhook secret and both Price IDs.')

PLANS = {'trial':{'runs':5,'seats':1},'starter':{'runs':30,'seats':3},'team':{'runs':100,'seats':10},'demo':{'runs':100,'seats':10}}
