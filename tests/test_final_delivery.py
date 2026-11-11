"""Fixture tests for delivery gates, integrity and output whitelist; not business acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import finalize_delivery as delivery

class DeliveryTests(unittest.TestCase):
    def state(self):
        project = {'stages': list(delivery.ds.STAGES)}
        state = {'stages': {s: {'rounds': [{'number': 1, 'fingerprint': s, 'status': 'passed', 'method': 'agent', 'result': {'overall': 'pass'}}], 'confirmation': {'round': 1, 'fingerprint': s, 'status': 'accepted'}} for s in project['stages']}}
        return project, state

    def test_every_stage_required(self):
        project, state = self.state()
        self.assertEqual(len(delivery.check_gate(project, state)), 6)
        for stage in project['stages']:
            for bad in ['pending', 'stale', 'changes-requested', 'waived', 'awaiting-verification']:
                with self.subTest(stage=stage, status=bad):
                    altered = copy.deepcopy(state); altered['stages'][stage]['rounds'][-1]['status'] = bad
                    with self.assertRaises(ValueError): delivery.check_gate(project, altered)
            for key, value in [('status', 'pending'), ('round', 0), ('fingerprint', 'old')]:
                altered = copy.deepcopy(state); altered['stages'][stage]['confirmation'][key] = value
                with self.assertRaises(ValueError): delivery.check_gate(project, altered)
        for stage in project['stages']:
            altered = copy.deepcopy(state); altered['stages'].pop(stage)
            with self.assertRaises(ValueError): delivery.check_gate(project, altered)
        with self.assertRaises(ValueError): delivery.check_gate({'stages': ['code']}, state)

    def fixture(self, root):
        (root/'代码/src').mkdir(parents=True)
        (root/'代码/src/manifest.json').write_text('{"version":"1.0"}')
        (root/'代码/说明.html').write_text('<h1>使用说明</h1>')
        (root/'代码/src/.DS_Store').write_bytes(b'junk')
        reviewed = {'files/'+p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.name != '.DS_Store'}
        spec = {'artifacts': [{'type':'zip-tree','source':'代码/src','target':'app.zip','purpose':'安装'}, {'type':'file','source':'代码/说明.html','target':'说明.html','purpose':'使用'}]}
        return spec, {'snapshotHashes': reviewed}

    def test_whitelist_zip_and_tested_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec, test_round = self.fixture(root)
            captured = delivery.capture(root, spec, test_round)
            output = root/'output'; output.mkdir()
            manifest = delivery.write_payloads(output, captured, {'test':{'round':1,'fingerprint':'fixture'}})
            self.assertEqual({p.name for p in output.iterdir()}, {'app.zip','说明.html','交付清单.json'})
            with zipfile.ZipFile(output/'app.zip') as archive:
                self.assertEqual(archive.namelist(), ['manifest.json'])
                self.assertEqual(archive.read('manifest.json'), (root/'代码/src/manifest.json').read_bytes())
            self.assertEqual(manifest['artifacts'][0]['sha256'], hashlib.sha256((output/'app.zip').read_bytes()).hexdigest())
            (root/'代码/src/manifest.json').write_text('changed')
            with self.assertRaises(ValueError): delivery.capture(root, spec, test_round)

    def test_unreviewed_file_symlink_and_invalid_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec, test_round = self.fixture(root)
            for target in ['../escape', '/escape', 'a/b', 'a\\b', '交付清单.json', '交付清单.JSON', '.hidden']:
                altered = copy.deepcopy(spec); altered['artifacts'][0]['target'] = target
                with self.assertRaises(ValueError): delivery.capture(root, altered, test_round)
            for names in [('A.zip', 'a.zip'), ('Café.zip', 'Cafe\u0301.zip')]:
                altered = copy.deepcopy(spec)
                altered['artifacts'][0]['target'], altered['artifacts'][1]['target'] = names
                with self.assertRaises(ValueError): delivery.capture(root, altered, test_round)
            (root/'代码/src/new.js').write_text('untested')
            with self.assertRaises(ValueError): delivery.capture(root, spec, test_round)
            (root/'代码/src/new.js').unlink()
            (root/'代码/src/link').symlink_to(root/'代码/说明.html')
            with self.assertRaises(ValueError): delivery.capture(root, spec, test_round)

if __name__ == '__main__': unittest.main()
