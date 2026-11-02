"""Exercise generated template scripts in an offline DOM model, with no browser."""
import shutil
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import ds
import review_records as records
import test_review as fixtures


class ReviewHtmlTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Optional developer DOM check needs Node.js')
    def test_round_template_controls_and_generated_links(self):
        f = fixtures.ReviewTests()
        f.setUp()
        try:
            first = f.prepare()
            value = f.result(first)
            value.update(overall='needs_improvement', issues=[{
                'id': 'HTML-001', 'kind': 'question', 'severity': 'major', 'status': 'open',
                'description': 'Synthetic question for an offline interaction test',
                'source': 'output.md:1', 'evidence': 'Synthetic inspection evidence'}])
            value['items'][0]['result'] = 'fail'
            f.record(first, value)
            records.reply(f.root, NS(stage='prd', round=1, issue='HTML-001', by='Fixture owner',
                          disposition='answered', message='Actual fixture clarification', evidence='Fixture input'))
            second = f.prepare()
            value = f.result(second)
            value['verifications'] = [{'issueId': 'HTML-001', 'result': 'pass', 'evidence': 'Independent fixture verification'}]
            f.record(second, value)
            third = f.prepare()
            f.record(third)
            files = [f.root / '验收记录/验收记录总.html',
                     f.root / '验收记录/需求验收记录/第002轮.html',
                     f.root / '验收记录/需求验收记录/第003轮.html']
            result = subprocess.run([shutil.which('node'), str(Path(__file__).with_name('review_dom.cjs')), *map(str, files)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        finally:
            f.tearDown()
