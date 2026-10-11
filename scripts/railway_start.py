"""Railway runtime: persistent private pilot or fully configured SaaS, never a public demo."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def provision_pilot(settings):
    from backend.store import Store
    from backend.auth import Identity
    if settings.launch_mode != 'private-pilot':
        return
    store = Store(settings.database)
    if store.one('SELECT id FROM users LIMIT 1'):
        return  # Restarts never overwrite credentials, memberships or research.
    address = os.getenv('FLAVO_PILOT_EMAIL', '')
    secret = os.getenv('FLAVO_PILOT_PASSWORD', '')
    if not address or not secret:
        raise RuntimeError('First private-pilot boot needs FLAVO_PILOT_EMAIL and FLAVO_PILOT_PASSWORD in Railway Variables.')
    account = Identity(store, settings).create({'name':'Pilot owner','company':'FLAVO Pilot','email':address,'password':secret})
    # This account is explicitly provisioned by the deployment operator, not self-registered.
    with store.tx() as db:
        db.execute('UPDATE users SET verified=1 WHERE id=?', (account['user'],))
        store.audit(db, account['workspace'], account['user'], 'pilot.provisioned')


def main():
    if os.getenv('FLAVO_ENV') != 'production':
        raise RuntimeError('Railway must use FLAVO_ENV=production; development accounts cannot be published.')
    if not os.getenv('FLAVO_PUBLIC_URL') and os.getenv('RAILWAY_PUBLIC_DOMAIN'):
        os.environ['FLAVO_PUBLIC_URL'] = 'https://' + os.environ['RAILWAY_PUBLIC_DOMAIN']
    mount = Path(os.getenv('RAILWAY_VOLUME_MOUNT_PATH', ''))
    if str(mount) != '/app/var' or not mount.is_dir():
        raise RuntimeError('Attach a persistent Railway volume at /app/var before starting the service.')
    # Railway mounts volumes as root. Own only our dedicated data directory, then drop root.
    if os.geteuid() == 0:
        import pwd
        account = pwd.getpwnam('flavo')
        os.chown(mount, account.pw_uid, account.pw_gid)
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    from backend.config import Settings
    settings = Settings()
    settings.validate()
    if Path(settings.database).parent.resolve() != mount.resolve():
        raise RuntimeError('FLAVO_DATABASE must be stored on the persistent Railway volume.')
    provision_pilot(settings)
    os.environ.pop('FLAVO_PILOT_PASSWORD', None)
    os.execv(sys.executable, [sys.executable, str(ROOT/'serve.py'), '--host', '0.0.0.0', '--port', os.getenv('PORT', '4175')])


if __name__ == '__main__':
    main()
