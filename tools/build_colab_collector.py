"""Build an inspectable, credential-free Colab canary from reviewed local code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import nbformat

ROOT = Path(__file__).resolve().parents[1]
WIN_BROWSER = "executable_path=r'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'"
QUIET = '''from contextlib import contextmanager
import logging
@contextmanager
def _quiet_scrapling():
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)
'''

MOUNT = '''from google.colab import auth, drive
from googleapiclient.discovery import build
import google.auth
from pathlib import Path
import json

auth.authenticate_user()
credentials, _ = google.auth.default()
about = build('drive', 'v3', credentials=credentials).about().get(
    fields='user(emailAddress),storageQuota').execute()
assert about['user']['emailAddress'].lower() == 'ankitg.owa@gmail.com', 'Wrong Drive account: stop here'
quota = about.get('storageQuota', {})
limit = int(quota.get('limit', 0))
assert limit >= 5_000_000_000_000, '5 TB entitlement not verified: stop here'
print({'account': about['user']['emailAddress'], 'quota_bytes': limit,
       'used_bytes': quota.get('usage'), 'runtime': 'standard CPU only'})
# Google asks for explicit consent; this permits this notebook to access Drive.
# The reviewed code below only writes into its new CompSetStudio/collection-runs folder.
drive.mount('/content/drive')
DRIVE_ROOT = Path('/content/drive/MyDrive/CompSetStudio/collection-runs')
assert Path('/content/drive/MyDrive').is_dir(), 'Drive mount missing'
'''

INSTALL = '''import subprocess, sys
assert 'google.colab' in sys.modules, 'Run this notebook in Colab, not the laptop'
subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet',
                'scrapling[fetchers]==0.4.15', 'playwright==1.63.0'],
               check=True, timeout=600)
subprocess.run([sys.executable, '-m', 'playwright', 'install', '--with-deps', 'chromium'],
               check=True, timeout=600)
print('Pinned collector dependencies installed; no model or paid API')
'''

CAPTURE = '''import os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import uuid

run_id = 'aketa-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
RUN = Path('/content/compset-runs') / run_id
assert not RUN.exists(), 'Never overwrite a prior run'
# The child process avoids the notebook event-loop conflict of sync Playwright.
# Only one fresh, anonymous direct Google session; no proxy or challenge retries.
command = [sys.executable, '-m', 'compset.google_calendar_network', '--output', str(RUN)]
environment = dict(os.environ, PYTHONPATH=str(PACKAGE_ROOT), PYTHONIOENCODING='utf-8')
try:
    completed = subprocess.run(command, cwd=PACKAGE_ROOT, env=environment,
                               capture_output=True, text=True, timeout=240)
    print({'collector_exit': completed.returncode, 'run_id': run_id})
except subprocess.TimeoutExpired:
    raise RuntimeError('Finite collector budget exhausted; do not retry automatically') from None
assert (RUN / 'latest.json').is_file(), 'No retained collector report: do not retry automatically'
report = json.loads((RUN / 'latest.json').read_text(encoding='utf-8'))
print({'state': report['state'], 'summary': report['summary'], 'stop_reason': report['stop_reason']})
if report.get('stop_reason'):
    print('Source attempt stopped; save diagnostics only. No challenge bypass or fallback.')
'''

PERSIST = '''import hashlib, json, shutil

allowed = ('calendar-capture.json', 'discovery.json', 'rendered-before-replay.json',
           'replay.json', 'api-calendar.json', 'latest.json', 'rates.csv', 'calendar.csv')
DRIVE_ROOT.mkdir(parents=True, exist_ok=True)
destination = DRIVE_ROOT / run_id
destination.mkdir(exist_ok=False)
proof = {'run_id': run_id, 'method': 'Colab standard CPU -> explicitly mounted Drive',
         'source_manifest': source_manifest, 'state': report['state'], 'summary': report['summary'],
         'scope': 'Aketa 30-day indicative canary only', 'files': {},
         'not_acquired': ['365-day coverage', 'peer hotel rates', 'complete OTA quotes',
                         'verified taxes/fees breakup', 'monthly ten-date verification']}
for name in allowed:
    source = RUN / name
    if not source.is_file():
        continue
    content = source.read_bytes()
    assert len(content) <= 2_000_000, 'Unexpectedly large output; stop before export'
    digest = hashlib.sha256(content).hexdigest()
    target = destination / name
    with target.open('xb') as stream:
        stream.write(content)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest, 'Drive round-trip mismatch'
    proof['files'][name] = {'bytes': len(content), 'sha256': digest, 'reread_verified': True}
with (destination / 'receipt.json').open('x', encoding='utf-8') as stream:
    json.dump(proof, stream, indent=2)
assert proof['files'], 'No output exported'
print({'drive_folder': str(destination), 'verified_files': len(proof['files']),
       'summary': proof['summary'], 'not_acquired': proof['not_acquired']})
# Original VM files are retained too; no move/delete if Drive is interrupted.
'''


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build():
    sources = {name: (ROOT / 'compset' / name).read_text(encoding='utf-8')
               for name in ('hotel_aketa.py', 'google_calendar_network.py')}
    network = sources['google_calendar_network.py']
    if network.count(WIN_BROWSER) != 1:
        raise ValueError('Reviewed browser portability anchor changed')
    portable = network.replace(WIN_BROWSER, 'executable_path=None')
    manifest = {name: {'original_sha256': sha(code), 'packaged_sha256': sha(
        portable if name == 'google_calendar_network.py' else code)}
        for name, code in sources.items()}
    modules = {'compset/__init__.py': '', 'compset/collect.py': QUIET,
               'compset/hotel_aketa.py': sources['hotel_aketa.py'],
               'compset/google_calendar_network.py': portable}
    for name, code in modules.items():
        compile(code, name, 'exec')
    bootstrap = ('import hashlib, json, sys\nfrom pathlib import Path\n'
                 'PACKAGE_ROOT = Path("/content/compset-colab-package")\n'
                 f'source_manifest = {manifest!r}\n'
                 f'modules = {modules!r}\n'
                 'for name, code in modules.items():\n'
                 '    target = PACKAGE_ROOT / name\n'
                 '    target.parent.mkdir(parents=True, exist_ok=True)\n'
                 '    if target.exists():\n'
                 '        assert target.read_text(encoding="utf-8") == code, "Source drift: stop"\n'
                 '    else:\n'
                 '        with target.open("x", encoding="utf-8") as stream:\n'
                 '            stream.write(code)\n'
                 '    if target.name in source_manifest:\n'
                 '        actual = hashlib.sha256(target.read_bytes()).hexdigest()\n'
                 '        assert actual == source_manifest[target.name]["packaged_sha256"]\n'
                 'print({"verified_modules": len(modules), "source_manifest": source_manifest})\n')
    md = nbformat.v4.new_markdown_cell
    cell = nbformat.v4.new_code_cell
    notebook = nbformat.v4.new_notebook(cells=[
        md('# CompSet Studio — Aketa Colab → Drive canary\n\n## Goal\n'
           'Run one finite public calendar collection on standard CPU and save sanitized '
           'JSON/CSV plus digest evidence in **ankitg.owa** Drive. Not executed yet.\n\n'
           'Current adapter: Aketa, INR, one adult, zero children, requested one room, '
           '30 dates. Prices are indicative minima, not final payable quotes.\n\n'
           'Requested follow-on scope remains **Aketa + six evidenced peers**, 365-day '
           'minimums, 30-day OTA details and ten monthly breakup checks. This canary '
           'does not implement or claim those uncollected observations.'),
        md('## Setup\n### 1. Verify storage and explicitly mount Drive\n'
           'Use the named account and standard CPU. Google requires normal sign-in/consent. '
           'No paid upgrade, remote runtime, proxy or keepalive. Drive consent allows '
           'notebook code broad file access; this reviewed package only writes its new run folder.'),
        cell(MOUNT),
        md('### 2. Install pinned public dependencies'), cell(INSTALL),
        md('### 3. Restore the reviewed package\n'
           'Only the Windows browser executable is replaced by Playwright-managed Chromium. '
           'The original parser and source-stop rules stay intact. Original and derived hashes '
           'make that portability change auditable. No credentials, raw conversations or private '
           'pairing material are embedded.'), cell(bootstrap),
        md('## Steps\n### 4. Collect one new calendar\n'
           'At most 240 seconds. Stop on controls/identity/context drift, a challenge, '
           '401/403/429 or source failure. Do not repeatedly rerun the collection cell.'), cell(CAPTURE),
        md('## Checks\n### 5. Copy allowed outputs and re-read their digests\n'
           'Each run gets a new folder. Unknown values stay unknown; prior source timestamps '
           'are not refreshed by copying. No opaque request bodies/cookies/headers are exported.'), cell(PERSIST),
        md('## Next Steps\nColab execution, rendered output inspection and Drive round-trip '
           'remain unverified until these cells actually run. Extend only after the canary: '
           'verify peer Google identities, inspect normal month navigation, implement bounded '
           'serial coverage/checkpoints, and compare actual supplier quotes for taxes/fees. '
           'A Google minimum is not the proven lowest price across the entire internet.')],
        metadata={'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                  'language_info': {'name': 'python'}, 'colab': {'name': 'CompSet-Aketa-Colab.ipynb'}})
    nbformat.validate(notebook)
    for item in notebook.cells:
        if item.cell_type == 'code':
            compile(item.source, '<notebook>', 'exec')
    return notebook


def main():
    notebook = build()
    target = ROOT / 'notebooks' / 'CompSet-Aketa-Colab.ipynb'
    target.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, target)
    print(json.dumps({'notebook': str(target), 'cells': len(notebook.cells),
                      'bytes': target.stat().st_size, 'executed': False,
                      'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
