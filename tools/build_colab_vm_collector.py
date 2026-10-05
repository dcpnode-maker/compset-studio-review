"""Package the reviewed Aketa canary for Colab VM-only export, without Drive access."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import nbformat

from tools.build_colab_collector import build as build_drive

ROOT = Path(__file__).resolve().parents[1]

PREFLIGHT = '''import os, platform, shutil, sys
from pathlib import Path
import google.colab

assert Path('/content').is_dir(), 'Use a Colab cloud VM for this notebook'

def read_limit(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None

quota = read_limit('/sys/fs/cgroup/cpu.max')
cpu_quota = None
if quota:
    parts = quota.split()
    if len(parts) == 2 and parts[0] != 'max':
        cpu_quota = int(parts[0]) / int(parts[1])
memory = read_limit('/sys/fs/cgroup/memory.max')
memory_limit = int(memory) if memory and memory.isdigit() else None
affinity = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None
host_memory = None
for line in (read_limit('/proc/meminfo') or '').splitlines():
    if line.startswith('MemTotal:'):
        host_memory = int(line.split()[1]) * 1024
visible_cpu = os.cpu_count()
caps = [value for value in (visible_cpu, affinity, cpu_quota) if value is not None]
resource_receipt = {'runtime': 'Colab-compatible runtime', 'cloud_placement_attested': False,
    'platform': platform.platform(),
    'python': platform.python_version(), 'visible_logical_cpus': visible_cpu,
    'affinity_cpus': affinity, 'cgroup_cpu_quota': cpu_quota,
    'effective_cpu_upper_bound': min(caps) if caps else None,
    'cgroup_memory_limit_bytes': memory_limit,
    'host_visible_memory_bytes': host_memory,
    'free_vm_disk_bytes': shutil.disk_usage('/content').free,
    'gpu_requested': False, 'paid_upgrade_requested': False}
print(resource_receipt)
assert resource_receipt['free_vm_disk_bytes'] >= 3_000_000_000, 'Insufficient VM disk: stop'
# This checks this VM only; it does not describe Codex Cloud, Colab guarantees or your plan.
'''

EXPORT = '''import hashlib, json, zipfile
from google.colab import files

allowed = ('calendar-capture.json', 'discovery.json', 'rendered-before-replay.json',
           'replay.json', 'api-calendar.json', 'latest.json', 'rates.csv', 'calendar.csv')
proof = {'run_id': run_id, 'method': 'Colab VM -> downloaded sanitized ZIP',
    'source_manifest': source_manifest, 'runtime_resources': resource_receipt,
    'state': report['state'], 'summary': report['summary'],
    'scope': 'Aketa 30-day indicative canary only', 'files': {},
    'not_acquired': ['365-day coverage', 'peer hotel rates', 'complete OTA quotes',
                     'verified taxes/fees breakup', 'monthly ten-date verification']}
contents = {}
for name in allowed:
    source = RUN / name
    if not source.is_file():
        continue
    content = source.read_bytes()
    assert len(content) <= 2_000_000, 'Unexpectedly large output: stop before export'
    contents[name] = content
    proof['files'][name] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
assert contents, 'No sanitized outputs to export'
archive = RUN.parent / (run_id + '.zip')
with archive.open('xb') as stream:
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in contents.items():
            bundle.writestr(name, content)
        bundle.writestr('receipt.json', json.dumps(proof, indent=2))
with zipfile.ZipFile(archive) as bundle:
    assert set(bundle.namelist()) == set(contents) | {'receipt.json'}
    for name, item in proof['files'].items():
        assert hashlib.sha256(bundle.read(name)).hexdigest() == item['sha256'], 'ZIP round-trip mismatch'
print({'archive': str(archive), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
       'verified_files': len(contents), 'not_acquired': proof['not_acquired']})
files.download(str(archive))
# No Drive mount, credentials, account-wide file access, overwrite or automatic rerun.
'''


def build():
    notebook = build_drive()
    notebook.cells[0].source = (
        '# CompSet Studio — Aketa cloud VM canary\n\n'
        'Run one finite public collection on a standard Colab CPU VM and download a sanitized ZIP. '
        '**Prepared locally; cloud execution has not been verified.**\n\n'
        'Scope: one Aketa Google indicative calendar, INR, one adult, requested one room, 30 dates. '
        'The complete 17-hotel/365-day calendar and detailed OTA coverage remain unfinished. '
        'No Drive permission or model API is required by these cells.')
    notebook.cells[1].source = (
        '## 1. Inspect this cloud VM\n\n'
        'Use standard CPU. The receipt records visible CPUs, Linux quotas, memory limits and free disk. '
        'Host-visible resources and container limits are reported separately. '
        'This package requests no GPU, paid upgrade or credentials.')
    notebook.cells[2].source = PREFLIGHT
    notebook.cells[9].source = (
        '## 5. Download sanitized results\n\n'
        'Export only eight allowlisted files plus a resource/source receipt; verify ZIP hashes before download. '
        'Keep original source timestamps and unknowns. No opaque request bodies, session headers or cookies are exported.')
    notebook.cells[10].source = EXPORT
    notebook.cells[11].source = (
        '## Remaining work\n\n'
        'Run and inspect this canary before extending it. Verify all peer provider identities, '
        'normal future-month navigation and bounded serial checkpointing. '
        'Google minima do not establish the lowest payable rate across all OTAs. '
        'The package remains separate from Yellow PMS/CRS builds.')
    notebook.metadata['colab']['name'] = 'CompSet-Aketa-Colab-VM.ipynb'
    nbformat.validate(notebook)
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            compile(cell.source, '<cloud-vm-cell>', 'exec')
    return notebook


def main():
    target = ROOT / 'notebooks' / 'CompSet-Aketa-Colab-VM.ipynb'
    target.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(build(), target)
    print(json.dumps({'notebook': str(target), 'executed': False,
                      'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
