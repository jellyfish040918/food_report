"""The cloud model must never report healthy with an empty model directory."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which('sh')
if not SHELL and os.name == 'nt':
    candidate = Path('C:/Program Files/Git/bin/bash.exe')
    if candidate.exists():
        SHELL = str(candidate)


@unittest.skipUnless(SHELL, 'A POSIX shell is required for the container entrypoint test.')
class ModelStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.tmp' if (ROOT / '.tmp').exists() else None)
        self.root = Path(self.temp.name)
        self.models = self.root / 'models'
        self.models.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        command = self.bin / 'ollama'
        command.write_text('#!/bin/sh\nprintf "fake-run:%s\\n" "$*"\n', encoding='utf-8')
        command.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_model(self):
        env = {**os.environ, 'FLAVO_MODEL':'qwen3.5:9b', 'OLLAMA_MODELS':self.models.as_posix()}
        # Bash converts the Windows inherited PATH. Prepend our fixture in POSIX syntax.
        fixture = self.bin.as_posix()
        if os.name == 'nt':
            fixture = '/' + fixture[0].lower() + fixture[2:]
        return subprocess.run([SHELL, '-c', 'export PATH="$1:$PATH"; exec sh "$2"',
                               'model-test', fixture, (ROOT / 'deploy/start-model.sh').as_posix()],
                              env=env, capture_output=True, text=True, timeout=10)

    def manifest(self):
        path = self.models / 'manifests/registry.ollama.ai/library/qwen3.5/9b'
        path.parent.mkdir(parents=True)
        path.write_text('{}')
        (self.models / 'blobs').mkdir()

    def test_empty_directory_fails_without_starting_model_server(self):
        result = self.run_model()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('files are missing', result.stderr)
        self.assertNotIn('fake-run:', result.stdout)

    def test_manifest_without_weights_fails(self):
        self.manifest()
        result = self.run_model()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('weights are missing', result.stderr)

    def test_packaged_model_starts_server(self):
        self.manifest()
        (self.models / 'blobs/sha256-fixture').write_bytes(b'fixture')
        result = self.run_model()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('fake-run:serve', result.stdout)

    def test_different_runtime_model_cannot_start_against_wrong_weights(self):
        self.manifest()
        (self.models / 'blobs/sha256-fixture').write_bytes(b'fixture')
        (self.models / 'manifests/registry.ollama.ai/library/qwen3.5/9b').rename(
            self.models / 'manifests/registry.ollama.ai/library/qwen3.5/other')
        result = self.run_model()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('files are missing', result.stderr)
