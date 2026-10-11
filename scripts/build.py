"""Build a portable static site, without publishing the raw input data."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
OUT.mkdir(exist_ok=True)
for name in ['index.html']:
    shutil.copy2(ROOT / name, OUT / name)
target = OUT / 'src'
target.mkdir(exist_ok=True)
for name in ['app.mjs', 'chat.mjs', 'engine.mjs', 'i18n.mjs', 'icons.mjs', 'views.mjs', 'figures.mjs', 'report-en.mjs', 'styles.css', 'theme.css', 'agent.mjs', 'agent.css', 'service.mjs', 'account.mjs', 'saas.css', 'method.mjs', 'studio.css', 'shutterstock_1867661479.jpg', '1.png', '2.png', '3.png', '6.png', '9.png']:
    shutil.copy2(ROOT / 'src' / name, target / name)
(target / 'generated').mkdir(exist_ok=True)
shutil.copy2(ROOT / 'src' / 'generated' / 'data.json', target / 'generated' / 'data.json')
(target / 'geo').mkdir(exist_ok=True)
shutil.copy2(ROOT / 'src' / 'geo' / 'world.json', target / 'geo' / 'world.json')
(OUT / '.nojekyll').touch()
print(f'Built {OUT}: {sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()):,} bytes')
