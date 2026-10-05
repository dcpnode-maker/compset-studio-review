import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import nbformat
from tools.build_colab_vm_collector import build, EXPORT


class ColabVMCollectorTests(unittest.TestCase):
    def test_valid_unexecuted_notebook_has_no_drive_auth_and_retains_finite_collector(self):
        notebook = build()
        nbformat.validate(notebook)
        code = '\n'.join(cell.source for cell in notebook.cells if cell.cell_type == 'code')
        self.assertNotIn('authenticate_user', code)
        self.assertNotIn('drive.mount', code)
        self.assertNotIn('googleapiclient', code)
        self.assertIn('timeout=240', code)
        for cell in notebook.cells:
            if cell.cell_type == 'code':
                compile(cell.source, '<test>', 'exec')
                self.assertIsNone(cell.execution_count)
                self.assertEqual(cell.outputs, [])

    def test_export_excludes_opaque_files_and_checks_digest_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / 'unique-run'
            run.mkdir()
            content = b'{"state":"unknown"}'
            (run / 'latest.json').write_bytes(content)
            (run / 'replay-command.json').write_text('private transport', encoding='utf-8')
            (run / 'cookies.json').write_text('private cookies', encoding='utf-8')
            downloads = []
            fake_colab = type('Colab', (), {'files': type('Files', (), {'download': downloads.append})})
            namespace = {'RUN': run, 'run_id': 'unique-run', 'source_manifest': {},
                         'resource_receipt': {'cgroup_memory_limit_bytes': None},
                         'report': {'state': 'unknown', 'summary': {}}, 'print': lambda *args: None}
            with patch.dict('sys.modules', {'google.colab': fake_colab}):
                exec(EXPORT, namespace)
            self.assertEqual(downloads, [str(Path(temp) / 'unique-run.zip')])
            with zipfile.ZipFile(downloads[0]) as bundle:
                self.assertEqual(set(bundle.namelist()), {'latest.json', 'receipt.json'})
                receipt = json.loads(bundle.read('receipt.json'))
                self.assertEqual(receipt['files']['latest.json']['sha256'], hashlib.sha256(content).hexdigest())
                self.assertIn('365-day coverage', receipt['not_acquired'])
            with patch.dict('sys.modules', {'google.colab': fake_colab}):
                with self.assertRaises(FileExistsError):
                    exec(EXPORT, namespace)

    def test_oversized_output_stops_before_zip_or_download(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / 'run'
            run.mkdir()
            (run / 'latest.json').write_bytes(b'x' * 2_000_001)
            namespace = {'RUN': run, 'run_id': 'run', 'source_manifest': {},
                         'resource_receipt': {}, 'report': {'state': 'unknown', 'summary': {}}}
            fake_colab = type('Colab', (), {'files': None})
            with patch.dict('sys.modules', {'google.colab': fake_colab}):
                with self.assertRaises(AssertionError):
                    exec(EXPORT, namespace)
            self.assertFalse((Path(temp) / 'run.zip').exists())


if __name__ == '__main__':
    unittest.main()
