"""Build a portable static site, without publishing the raw input data."""
import argparse
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--pages', action='store_true', help='Build the public product site and API-free research samples.')
pages = parser.parse_args().pages
OUT = ROOT / ('dist-pages' if pages else 'dist')
if pages and OUT.exists():
    # This fixed build directory must remain inside the repository, including on Windows.
    if OUT.is_symlink() or OUT.resolve().parent != ROOT.resolve():
        raise RuntimeError('Refusing to replace a build directory outside the repository.')
    shutil.rmtree(OUT)
OUT.mkdir(exist_ok=True)
for name in ['index.html']:
    html = (ROOT / name).read_text(encoding='utf-8')
    if pages:
        html = html.replace('./src/app.mjs', './src/preview.mjs')
        html = html.replace('</head>', '  <meta name="flavo-mode" content="public-preview">\n  <link rel="stylesheet" href="./src/preview.css">\n  <link rel="stylesheet" href="./src/marketing.css">\n</head>')
    (OUT / name).write_text(html, encoding='utf-8')
target = OUT / 'src'
target.mkdir(exist_ok=True)
assets = ['engine.mjs', 'i18n.mjs', 'icons.mjs', 'views.mjs', 'figures.mjs', 'report-en.mjs', 'styles.css', 'theme.css', 'agent.css', 'saas.css', 'method.mjs', 'studio.css', 'shutterstock_1867661479.jpg', '1.png', '2.png', '3.png', '6.png', '9.png']
assets += ['corporate.css', 'presentation.mjs']
assets += ['preview.mjs', 'preview.css', 'marketing.mjs', 'marketing.css', 'portal.mjs'] if pages else ['app.mjs', 'chat.mjs', 'agent.mjs', 'service.mjs', 'account.mjs', 'entry.mjs']
for name in assets:
    shutil.copy2(ROOT / 'src' / name, target / name)
(target / 'generated').mkdir(exist_ok=True)
shutil.copy2(ROOT / 'src' / 'generated' / 'data.json', target / 'generated' / 'data.json')
if pages:
    # This is a public navigation origin, never an API key or a cross-origin auth endpoint.
    app_url = os.getenv('FLAVO_APP_URL', '').strip().rstrip('/')
    if app_url:
        url = urlparse(app_url)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError('FLAVO_APP_URL must be an HTTPS origin without path, credentials, query or fragment.')
    (target / 'generated' / 'site-config.json').write_text(json.dumps({'appUrl': app_url, 'launchMode': 'saas' if os.getenv('FLAVO_SITE_LAUNCH_MODE') == 'saas' else 'private-pilot'}), encoding='utf-8')
(target / 'geo').mkdir(exist_ok=True)
shutil.copy2(ROOT / 'src' / 'geo' / 'world.json', target / 'geo' / 'world.json')
(OUT / '.nojekyll').touch()
print(f'Built {OUT}: {sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()):,} bytes')
