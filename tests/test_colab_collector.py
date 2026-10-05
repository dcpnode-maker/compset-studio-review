import hashlib
import json
import unittest
import nbformat
from tools.build_colab_collector import build, WIN_BROWSER


class ColabCollectorTests(unittest.TestCase):
    def test_notebook_valid_code_compiles_and_stays_unexecuted(self):
        notebook = build()
        nbformat.validate(notebook)
        for cell in notebook.cells:
            if cell.cell_type == 'code':
                compile(cell.source, '<cell>', 'exec')
                self.assertIsNone(cell.execution_count)
                self.assertEqual(cell.outputs, [])

    def test_package_is_fixed_allowlist_and_only_network_portability_change(self):
        bootstrap = build().cells[6].source
        # Execute only locally authored package metadata prefix, not collector/network cells.
        prefix = bootstrap.split('for name, code in modules.items():', 1)[0]
        namespace = {}
        exec(prefix, namespace)
        modules, manifest = namespace['modules'], namespace['source_manifest']
        self.assertEqual(set(modules), {'compset/__init__.py', 'compset/collect.py',
                                       'compset/hotel_aketa.py', 'compset/google_calendar_network.py'})
        self.assertNotIn(WIN_BROWSER, modules['compset/google_calendar_network.py'])
        self.assertIn('executable_path=None', modules['compset/google_calendar_network.py'])
        for name in ('hotel_aketa.py', 'google_calendar_network.py'):
            digest = hashlib.sha256(modules['compset/' + name].encode()).hexdigest()
            self.assertEqual(digest, manifest[name]['packaged_sha256'])
        self.assertEqual(manifest['hotel_aketa.py']['original_sha256'],
                         manifest['hotel_aketa.py']['packaged_sha256'])

    def test_identity_quota_export_and_finite_boundaries_present(self):
        cells = '\n'.join(c.source for c in build().cells if c.cell_type == 'code')
        for marker in ("ankitg.owa@gmail.com", '5_000_000_000_000', 'timeout=240',
                       "target.open('xb')", 'reread_verified', 'not_acquired'):
            self.assertIn(marker, cells)
        self.assertNotIn('api_key', cells.lower())
        self.assertNotIn('replay-command.json', build().cells[10].source)
        self.assertNotIn('unlink(', cells)


if __name__ == '__main__':
    unittest.main()
