"""The public artifact must not contain server entry points or stale private files."""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PagesBuildTests(unittest.TestCase):
    def test_isolated_public_build_and_project_subpath_assets(self):
        original = (ROOT / 'index.html').read_bytes()
        out = ROOT / 'dist-pages'
        out.mkdir(exist_ok=True)
        (out / 'private-sentinel.txt').write_text('disposable build residue', encoding='utf-8')
        subprocess.run([sys.executable, str(ROOT / 'scripts/build.py'), '--pages'], cwd=ROOT, check=True, capture_output=True)
        self.assertFalse((out / 'private-sentinel.txt').exists())
        self.assertEqual((ROOT / 'index.html').read_bytes(), original)
        html = (out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('src/preview.mjs', html)
        self.assertIn('public-preview', html)
        for asset in re.findall(r'(?:src|href)="(\./[^\"]+)"', html):
            self.assertTrue((out / asset).is_file(), asset)
        for module in (out / 'src').glob('*.mjs'):
            for dependency in re.findall(r"from ['\"](\./[^'\"]+)['\"]", module.read_text(encoding='utf-8')):
                self.assertTrue((module.parent / dependency).is_file(), dependency)
        for forbidden in ['backend', 'data', 'var', '.env', 'src/app.mjs', 'src/service.mjs', 'src/account.mjs', 'src/chat.mjs']:
            self.assertFalse((out / forbidden).exists(), forbidden)
        self.assertTrue((out / 'src/generated/data.json').is_file())
        self.assertTrue((out / 'src/geo/world.json').is_file())
