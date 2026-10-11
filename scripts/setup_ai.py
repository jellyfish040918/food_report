"""Prepare the local inference service once when the app launcher runs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import Settings  # Load the same .env as the API before the adapter.
import server

def prepare():
    try:
        server.ollama('/api/tags')
    except OSError:
        if urlparse(server.OLLAMA_HOST).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('The configured inference server is unreachable.')
        executable = shutil.which('ollama')
        candidate = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Ollama' / 'ollama.exe'
        if not executable and candidate.exists():
            executable = str(candidate)
        if not executable:
            raise RuntimeError('Install the local inference runtime from https://ollama.com/download first.')
        (ROOT / '.tmp').mkdir(exist_ok=True)
        with (ROOT / '.tmp' / 'ai-runtime.log').open('a', encoding='utf-8') as log:
            subprocess.Popen([executable, 'serve'], stdout=log, stderr=log,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        for _ in range(30):
            time.sleep(1)
            try:
                server.ollama('/api/tags')
                break
            except OSError:
                pass
        else:
            raise RuntimeError('The local inference service did not start. See .tmp/ai-runtime.log.')
    model, _ = server.select_model()
    if not model:
        model = server.PREFERRED_MODEL
        print(f'Preparing FLAVO AI: {model}. Downloading or resuming model files; this may take time on the first launch.', flush=True)
        request = urllib.request.Request(server.OLLAMA_HOST + '/api/pull',
            data=json.dumps({'model': model, 'stream': True}).encode(), headers={'Content-Type': 'application/json'})
        last_update = 0
        with urllib.request.urlopen(request, timeout=1800) as response:
            for line in response:
                progress = json.loads(line)
                if progress.get('error'):
                    raise RuntimeError(progress['error'])
                if time.monotonic() - last_update > 5 or progress.get('status') == 'success':
                    percent = f" {progress.get('completed', 0) / progress['total'] * 100:.0f}%" if progress.get('total') else ''
                    print(progress.get('status', 'Preparing') + percent, flush=True)
                    last_update = time.monotonic()
        server.model_details.cache_clear()
        model, _ = server.select_model()
        if not model:
            raise RuntimeError('No compatible local text generation model is available.')
    print(f'FLAVO AI ready: {model}', flush=True)

if __name__ == '__main__':
    try:
        prepare()
    except (OSError, ValueError, RuntimeError) as error:
        print(f'AI setup failed: {error}', file=sys.stderr)
        sys.exit(1)
