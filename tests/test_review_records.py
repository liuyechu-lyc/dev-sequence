"""Behavioral tests for review layout, replies, frozen evidence and handoffs."""
import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import ds
import review_records as records


class ReviewRecordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ds-records-')
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'input.md').write_text('# Synthetic fixture\nInitial artifact.\n')
        self.run_cli('init', '--stages', 'prd,ui')

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, ok=True):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ds.main(['--project', str(self.root), *map(str, args)])
        if ok:
            self.assertIn(code, (0, 2), err.getvalue())
            return json.loads(out.getvalue())
        self.assertEqual(code, 1, out.getvalue())
        return json.loads(err.getvalue())

    def prepare(self, stage='prd', method='human', kind='review', select=True,
                choice_method=None, reuse='once', ok=True):
        spec = {'artifacts': [{'path': 'input.md', 'version': 'fixture-v1'}],
                'context': [], 'scope': {'description': 'Synthetic behavioral fixture', 'exclusions': []},
                'checklist': [{'id': 'CHECK-1', 'text': 'Inspect fixture', 'kind': 'semantic'}]}
        if stage == 'test':
            self.run_cli('init', '--stages', 'test')
            spec['context'] = [{'role': role, 'path': 'input.md', 'version': 'fixture-v1'}
                               for role in ('prd', 'prototype', 'tech', 'code')]
        path = self.root / 'request.json'
        path.write_text(json.dumps(spec))
        if select and kind == 'review' and method != 'script':
            history = ds.database(self.root)['stages'][stage].get('reviewChoices', [])
            self.choose(choice_method or ('native' if method == 'agent' else 'third-party'),
                        stage=stage, reuse=reuse, source='synthetic explicit choice ' + str(len(history) + 1))
        extra = ['--producer-session', 'producer-fixture'] if stage == 'test' else []
        return self.run_cli('prepare', '--stage', stage, '--method', method, '--kind', kind, '--spec', path, *extra, ok=ok)

    def choose(self, method, stage='prd', reuse='once', source='synthetic explicit choice', ok=True):
        return self.run_cli('review-choice', '--stages', stage, '--method', method, '--reuse', reuse,
                            '--by', 'Fixture owner', '--source', source,
                            '--text', 'Synthetic user selects ' + method + '; reuse=' + reuse, ok=ok)

    def authorize_native(self):
        value = {'mode': 'review-only', 'stages': ['prd'], 'scope': 'Synthetic full delivery scope',
                 'authorization': {'by': 'Fixture owner', 'source': 'synthetic delivery request',
                                   'text': 'Complete the full chain, including implementation and testing'},
                 'allowed': {'review': True, 'notifyOrigin': True, 'repair': True, 'advance': False, 'autoConfirm': False}}
        path = self.root / 'automation-fixture.json';path.write_text(json.dumps(value))
        self.run_cli('automation', '--spec', path)

    def result(self, prepared, issues=None, passed=False):
        source = self.root / prepared['snapshot'] / 'result-template.json'
        result = json.loads(source.read_text())
        result.update(overall='pass' if passed else 'needs_improvement', summary='Synthetic fixture conclusion',
                      reviewer={'name': 'Fixture reviewer', 'sessionId': 'fixture-agent',
                                'freshContext': True, 'isolationEvidence': 'Synthetic validator fixture, not a production review'})
        result['items'] = [{'id': 'CHECK-1', 'result': 'pass' if passed else 'fail',
                            'evidence': 'Fixture inspection evidence', 'comment': ''}]
        result['issues'] = issues or []
        return result

    def submit(self, prepared, result):
        path = self.root / 'result.json'
        path.write_text(json.dumps(result, ensure_ascii=False))
        return self.run_cli('record', '--stage', prepared['stage'], '--round', prepared['round'], '--result', path)

    def issue(self, severity='major', kind='problem', status='open', issue_id='DF-001'):
        return {'id': issue_id, 'kind': kind, 'severity': severity, 'status': status,
                'description': 'A <tag> | issue </script><img src=x onerror=alert(1)>',
                'source': 'input.md:1', 'evidence': 'Observed fixture', 'resolution': 'Original recommendation'}

    def payload(self, path=None):
        path = path or self.root / '验收记录/验收记录总.html'
        matches = list(records.DATA_BLOCK.finditer(path.read_text()))
        self.assertEqual(len(matches), 1)
        return json.loads(matches[0][2])

    def test_visible_tree_and_process_files(self):
        prepared = self.prepare()
        top = self.root / '验收记录'
        self.assertEqual({p.name for p in top.iterdir() if p.is_file()}, {'验收记录总.md', '验收记录总.html'})
        self.assertEqual({p.name for p in top.iterdir() if p.is_dir()}, {'需求验收记录', 'UI验收记录'})
        folder = top / '需求验收记录'
        self.assertEqual({p.name for p in folder.iterdir() if p.is_file()}, {'第001轮.md', '第001轮.html'})
        work = self.root / records.process_dir('prd', 1)
        self.assertTrue((work / '验收请求.md').is_file())
        self.assertFalse(list(work.glob('*.html')))
        self.assertTrue((self.root / prepared['snapshot'] / 'manifest.json').is_file())
        self.assertTrue((self.root / records.state_path('验收数据.json')).is_file())

    def test_reply_updates_both_views_preserves_shell_and_frozen_source(self):
        prepared = self.prepare()
        outcome = self.submit(prepared, self.result(prepared, [self.issue()]))
        frozen = self.root / outcome['source']
        checksum = hashlib.sha256(frozen.read_bytes()).hexdigest()
        summary = self.root / '验收记录/验收记录总.html'
        detail = self.root / '验收记录/需求验收记录/第001轮.html'
        shells = {}
        for path in (summary, detail):
            value = path.read_text().replace('</style>', '/* project customization */\n</style>')
            path.write_text(value)
            shells[path] = records.DATA_BLOCK.sub('<DATA>', value)
        self.run_cli('reply', '--stage', 'prd', '--round', '1', '--issue', 'DF-001', '--by', 'Owner',
                     '--disposition', 'declined', '--message', '保持原行为，因为本期范围已排除', '--evidence', 'Human decision fixture')
        for path in (summary, detail):
            self.assertEqual(records.DATA_BLOCK.sub('<DATA>', path.read_text()), shells[path])
            self.assertIn('保持原行为', path.with_suffix('.md').read_text())
        self.assertEqual(hashlib.sha256(frozen.read_bytes()).hexdigest(), checksum)
        self.assertEqual(ds.database(self.root)['stages']['prd']['rounds'][0]['status'], 'changes-requested')
        self.assertEqual([h for h in self.payload()['stages'][0]['rounds'][0]['issues'][0]['history'] if h['type'] == 'reply'][0]['disposition'], 'declined')
        self.assertNotIn('</script><img', summary.read_text())
        self.assertIn('\\u003c/script>', summary.read_text())
        self.run_cli('reply', '--stage', 'prd', '--round', '1', '--issue', 'DF-001', '--by', 'Owner',
                     '--disposition', 'declined', '--message', '', ok=False)
        self.run_cli('reply', '--stage', 'prd', '--round', '1', '--issue', 'UNKNOWN', '--by', 'Owner',
                     '--disposition', 'fixed', '--message', 'Not a real issue', ok=False)

    def test_cross_round_issue_chain_and_phase_order(self):
        p1 = self.prepare()
        outcome = self.submit(p1, self.result(p1, [self.issue()]))
        source = self.root / outcome['source']
        frozen = source.read_bytes()
        self.run_cli('reply', '--stage', 'prd', '--round', '1', '--issue', 'DF-001',
                     '--by', 'Owner', '--disposition', 'fixed', '--message', '实际修复已完成',
                     '--evidence', 'input.md:1; synthetic fixture evidence')
        self.assertEqual(len(ds.database(self.root)['stages']['prd']['rounds']), 1)
        p2 = self.prepare()
        value = self.result(p2, passed=True)
        value['verifications'] = [{'issueId': 'DF-001', 'result': 'pass',
                                   'evidence': 'Independent fixture inspection', 'comment': 'Verified'}]
        self.assertEqual(self.submit(p2, value)['status'], 'passed')
        payload = self.payload()
        self.assertEqual([s['id'] for s in payload['stages']], ['prd', 'ui'])
        self.assertEqual([r['number'] for r in payload['stages'][0]['rounds']], [2, 1])
        current, original = payload['stages'][0]['rounds']
        self.assertEqual(current['issues'], [])
        self.assertEqual(current['followUps'][0]['issueId'], 'DF-001')
        self.assertEqual(original['issues'][0]['processingStatus'], 'verified')
        self.assertEqual([h.get('disposition', h.get('status')) for h in original['issues'][0]['history']],
                         ['open', 'fixed', 'verified'])
        first = self.payload(self.root / '验收记录/需求验收记录/第001轮.html')
        self.assertEqual(first['stages'][0]['rounds'][0]['issues'][0]['status'], 'open')
        self.assertEqual(source.read_bytes(), frozen)
        p3 = self.prepare()
        self.submit(p3, self.result(p3, passed=True))
        third = self.payload(self.root / '验收记录/需求验收记录/第003轮.html')['stages'][0]
        self.assertEqual(third['rounds'][0]['issues'], [])
        self.assertEqual(third['rounds'][0]['followUps'], [])
        self.assertEqual(third['pendingIssues'], [])
        self.assertNotIn('DF-001', (self.root / '验收记录/需求验收记录/第003轮.md').read_text())
        self.assertNotIn('DF-001', (self.root / '验收记录/需求验收记录/第003轮.html').read_text())

    def test_omitted_historical_blocker_cannot_pass_or_confirm(self):
        first = self.prepare()
        self.submit(first, self.result(first, [self.issue()]))
        self.run_cli('reply', '--stage', 'prd', '--round', '1', '--issue', 'DF-001', '--by', 'Owner',
                     '--disposition', 'declined', '--message', 'A response is not independent closure')
        later = self.prepare()
        outcome = self.submit(later, self.result(later, passed=True))
        self.assertEqual(outcome['status'], 'changes-requested')
        self.assertEqual(self.run_cli('status')['prd']['status'], 'changes-requested')
        self.run_cli('confirm', '--stage', 'prd', '--by', 'Owner', '--evidence', 'Cannot override blocker', ok=False)
        self.assertIn('DF-001', self.payload()['stages'][0]['rounds'][0]['validationReasons'][0])
        final = self.prepare()
        self.assertEqual(self.submit(final, self.result(final, [self.issue(status='verified')], passed=True))['status'], 'passed')

    def test_stale_and_confirmation_are_not_hidden(self):
        p = self.prepare()
        self.submit(p, self.result(p, passed=True))
        self.run_cli('confirm', '--stage', 'prd', '--by', 'Fixture owner', '--evidence', 'Explicit fixture acceptance')
        (self.root / 'input.md').write_text('Changed content\n')
        status = self.run_cli('status')
        self.assertEqual(status['prd']['status'], 'stale')
        self.assertEqual(status['prd']['confirmation']['status'], 'stale')
        self.assertEqual(self.payload()['stages'][0]['status'], 'stale')

    def test_raw_tamper_is_detected_but_view_update_is_not_tamper(self):
        p = self.prepare()
        outcome = self.submit(p, self.result(p, passed=True))
        frozen = self.root / outcome['source']
        value = json.loads(frozen.read_text())
        value['round']['result']['summary'] = 'Tampered'
        frozen.write_text(json.dumps(value))
        self.assertEqual(self.run_cli('status')['prd']['status'], 'stale')

    def test_legacy_state_is_read_without_moving_original(self):
        p = self.prepare()
        self.submit(p, self.result(p, [self.issue(severity='suggestion', kind='suggestion', issue_id='SG-1')]))
        path = self.root / records.state_path('验收数据.json')
        legacy = self.root / '验收记录/验收数据.json'
        legacy.write_bytes(path.read_bytes())
        path.unlink()
        old_view = self.root / '验收记录/验收记录.html'
        old_view.write_text('LEGACY FROZEN VIEW')
        before = legacy.read_bytes()
        self.run_cli('status')
        self.assertEqual(legacy.read_bytes(), before)
        self.assertEqual(old_view.read_text(), 'LEGACY FROZEN VIEW')
        self.assertTrue(path.exists())
        self.assertEqual(len(self.payload()['stages'][0]['rounds'][0]['issues']), 1)

    def test_handoff_native_uses_hidden_process_and_does_not_spawn_extra_html(self):
        auth = {'mode': 'review-only', 'stages': ['prd'], 'scope': 'Synthetic fixture',
                'authorization': {'by': 'Fixture owner', 'source': 'fixture input', 'text': 'Permit independent review fixture'},
                'allowed': {'review': True, 'notifyOrigin': True, 'repair': True, 'advance': False, 'autoConfirm': False}}
        policy = self.root / 'auth.json';policy.write_text(json.dumps(auth))
        self.run_cli('automation', '--spec', policy)
        p = self.prepare(method='agent')
        job = self.run_cli('handoff-open', '--stage', 'prd', '--round', p['round'])
        self.run_cli('handoff-bind', '--job', job['job'], '--reviewer', 'fixture-agent', '--receipt', 'Synthetic spawn receipt')
        result = self.result(p, passed=True)
        path = self.root / 'result.json';path.write_text(json.dumps(result))
        envelope = self.run_cli('handoff-complete', '--job', job['job'], '--result', path)
        received = self.run_cli('handoff-receive', '--job', job['job'], '--sender', 'fixture-agent',
                                '--receipt', 'Synthetic completed envelope', '--inputs-ready', '--permissions-ready',
                                '--readiness-evidence', 'Synthetic validated inputs')
        self.assertEqual(received['action'], 'await-confirmation')
        work = self.root / records.process_dir('prd', 1)
        self.assertFalse(list(work.glob('*.html')))
        self.assertTrue((self.root / envelope['resultPath']).is_file())
        self.assertEqual({p.name for p in (self.root / '验收记录').iterdir() if p.is_file()}, {'验收记录总.md', '验收记录总.html'})

    def test_final_test_requires_actual_evidence_and_new_identity(self):
        p = self.prepare(stage='test', method='agent')
        result = self.result(p, passed=True)
        path = self.root / 'result.json';path.write_text(json.dumps(result))
        self.run_cli('record', '--stage', 'test', '--round', p['round'], '--result', path, ok=False)
        for filename in ['design.txt', 'execution.txt']:
            (self.root / filename).write_text('Synthetic validator evidence, not a product test result\n')
        result['independentTest'] = {'sessionId': 'fixture-agent', 'freshContext': True, 'designedHere': True, 'executedHere': True,
                                     'designEvidence': 'Synthetic design', 'executionEvidence': 'Synthetic execution',
                                     'testCaseIds': ['TC-fixture'], 'buildVersion': 'fixture', 'environment': 'fixture',
                                     'evidenceFiles': [{'path': name, 'kind': kind, 'sha256': hashlib.sha256((self.root/name).read_bytes()).hexdigest()}
                                                       for name, kind in [('design.txt','design'),('execution.txt','execution')]]}
        path.write_text(json.dumps(result))
        self.assertEqual(self.run_cli('record', '--stage', 'test', '--round', p['round'], '--result', path)['status'], 'passed')
        p2 = self.prepare(stage='test', method='agent')
        reused = self.result(p2, passed=True);reused['independentTest'] = result['independentTest']
        path.write_text(json.dumps(reused))
        self.run_cli('record', '--stage', 'test', '--round', p2['round'], '--result', path, ok=False)

    def test_html_shell_is_not_silently_replaced(self):
        path = self.root / '验收记录/验收记录总.html'
        path.write_text('<html>Unexpected custom page without data slot</html>')
        self.run_cli('status', ok=False)
        self.assertEqual(path.read_text(), '<html>Unexpected custom page without data slot</html>')

    def test_symlink_output_is_rejected(self):
        tmp = tempfile.TemporaryDirectory(prefix='ds-outside-')
        outside = Path(tmp.name)
        root = self.root / 'other';root.mkdir()
        (root / '验收记录').symlink_to(outside, target_is_directory=True)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = ds.main(['--project', str(root), 'init', '--stages', 'prd'])
        self.assertEqual(result, 1)
        self.assertFalse(list(outside.iterdir()))
        tmp.cleanup()

    def test_delivery_authorization_does_not_choose_review_method(self):
        self.authorize_native()
        error = self.prepare(method='agent', select=False, ok=False)
        self.assertIn('尚未选择验收方式', error['error'])
        self.assertEqual(ds.database(self.root)['stages']['prd']['rounds'], [])
        self.assertFalse((self.root / records.process_dir('prd', 1)).exists())
        self.prepare(method='human', select=False, ok=False)

    def test_third_party_cannot_dispatch_native(self):
        self.authorize_native()
        p = self.prepare(method='agent', choice_method='third-party')
        self.assertEqual(p['nextAction'], 'deliver-third-party')
        self.assertTrue((self.root / p['prompt']).is_file())
        error = self.run_cli('handoff-open', '--stage', 'prd', '--round', 1, ok=False)
        self.assertIn('本模型验收选择', error['error'])
        self.assertFalse((self.root / records.state_path('交接数据.json')).exists())

    def test_skip_keeps_unreviewed_and_blocks_review_and_confirmation(self):
        self.choose('skip')
        state = self.run_cli('status')['prd']
        self.assertEqual(state['status'], 'pending')
        self.assertEqual(state['reviewChoice']['method'], 'skip')
        self.assertEqual(ds.database(self.root)['stages']['prd']['rounds'], [])
        self.prepare(method='agent', select=False, ok=False)
        self.run_cli('confirm', '--stage', 'prd', '--by', 'Owner', '--evidence', 'skip is not pass', ok=False)
        self.assertEqual(self.payload()['stages'][0]['reviewChoice']['method'], 'skip')
        self.assertIn('不产生通过或豁免', (self.root / '验收记录/验收记录总.md').read_text())

    def test_once_choice_cannot_be_replenished_by_replay(self):
        p = self.prepare(method='agent')
        choice = self.run_cli('status')['prd']['reviewChoice']
        replay = self.choose('native', source=choice['authorization']['source'])
        self.assertTrue(replay['duplicate'])
        self.assertEqual(replay['choice'], choice['id'])
        self.assertEqual(choice['preparedRounds'], [p['round']])
        self.prepare(method='agent', select=False, ok=False)
        self.choose('third-party', source='synthetic later user message')
        self.choose('native', source=choice['authorization']['source'], ok=False)
        new = self.prepare(method='agent')
        self.assertEqual(new['round'], 2)

    def test_explicit_stage_reuse_does_not_extend_to_other_stage(self):
        first = self.prepare(method='agent', reuse='stage')
        second = self.prepare(method='agent', select=False)
        self.assertEqual(first['reviewChoice']['id'], second['reviewChoice']['id'])
        self.assertEqual(self.run_cli('status')['prd']['reviewChoice']['preparedRounds'], [1, 2])
        self.prepare(stage='ui', method='agent', select=False, ok=False)
        self.assertEqual(ds.database(self.root)['stages']['ui']['rounds'], [])

    def test_choice_change_blocks_binding_already_open_job(self):
        self.authorize_native()
        p = self.prepare(method='agent')
        job = self.run_cli('handoff-open', '--stage', 'prd', '--round', p['round'])
        self.choose('skip', source='synthetic withdrawal before dispatch')
        self.run_cli('handoff-bind', '--job', job['job'], '--reviewer', 'fixture-agent',
                     '--receipt', 'must not bind after changed choice', ok=False)
        ledger = json.loads((self.root / records.state_path('交接数据.json')).read_text())
        self.assertEqual(ledger['jobs'][job['job']]['state'], 'prepared')

    def test_changed_choice_keeps_real_result_but_stops_automation(self):
        self.authorize_native()
        p = self.prepare(method='agent')
        job = self.run_cli('handoff-open', '--stage', 'prd', '--round', p['round'])
        self.run_cli('handoff-bind', '--job', job['job'], '--reviewer', 'fixture-agent', '--receipt', 'synthetic spawn')
        result = self.result(p, passed=True)
        path = self.root / 'result.json';path.write_text(json.dumps(result))
        self.choose('third-party', source='synthetic choice changed while reviewer running')
        self.run_cli('handoff-complete', '--job', job['job'], '--result', path)
        received = self.run_cli('handoff-receive', '--job', job['job'], '--sender', 'fixture-agent',
                                '--receipt', 'synthetic real completion', '--inputs-ready', '--permissions-ready',
                                '--readiness-evidence', 'synthetic validated inputs')
        self.assertEqual(received['action'], 'await-user')
        state = self.run_cli('status')['prd']
        self.assertEqual(state['status'], 'passed')
        self.assertEqual(state['confirmation']['status'], 'pending')
        self.assertEqual(state['reviewChoice']['method'], 'third-party')

    def test_choice_requires_provenance_and_does_not_block_local_fix(self):
        self.run_cli('review-choice', '--stages', 'prd', '--method', 'native', '--by', 'Owner',
                     '--source', '', '--text', 'native', ok=False)
        self.assertIsNone(self.run_cli('status')['prd']['reviewChoice'])
        p = self.prepare(method='script', select=False)
        self.assertEqual(self.submit(p, self.result(p, passed=True))['status'], 'pending')
        self.prepare(method='human', kind='fix', select=False, ok=False)

    def test_late_old_result_displays_first_without_replacing_current_status(self):
        first = self.prepare()
        second = self.prepare()
        with patch('ds.now', return_value='2026-11-02T17:00:00+08:00'):
            self.submit(second, self.result(second))
        with patch('ds.now', return_value='2026-11-02T17:30:00+08:00'):
            self.submit(first, self.result(first, passed=True))
        source = ds.database(self.root)['stages']['prd']['rounds']
        self.assertEqual([r['number'] for r in source], [1, 2])
        stage = self.payload()['stages'][0]
        self.assertEqual([r['number'] for r in stage['rounds']], [1, 2])
        self.assertEqual(stage['status'], 'changes-requested')
        self.assertEqual(stage['rounds'][0]['status'], 'passed')
        self.assertEqual(self.run_cli('status')['prd']['status'], 'changes-requested')
        md = (self.root / '验收记录/验收记录总.md').read_text()
        self.assertLess(md.index('### 验收记录 第001轮'), md.index('### 验收记录 第002轮'))

    def test_display_time_order_normalizes_zones_and_has_stable_fallbacks(self):
        values = [
            {'number': 1, 'recordedAt': '2026-11-02T16:00:00+08:00'},
            {'number': 2, 'recordedAt': '2026-11-02T08:30:00Z'},
            {'number': 3, 'recordedAt': '2026-11-02T16:30:00+08:00'},
            {'number': 4, 'createdAt': '2026-11-02T17:00:00+08:00'},
            {'number': 5, 'recordedAt': 'legacy-invalid', 'createdAt': '2026-11-02T15:00:00+08:00'},
            {'number': 6}, {'number': 7, 'createdAt': 'unknown'},
        ]
        self.assertEqual([r['number'] for r in sorted(values, key=records.display_order, reverse=True)],
                         [4, 3, 2, 1, 5, 7, 6])


    def test_repeat_old_problem_is_compact_until_an_actual_change(self):
        first = self.prepare()
        self.submit(first, self.result(first, [self.issue()]))
        second = self.prepare()
        self.submit(second, self.result(second, [self.issue()]))
        latest = self.payload()['stages'][0]['rounds'][0]
        self.assertEqual(latest['issues'], [])
        self.assertEqual(latest['followUps'][0]['result'], 'fail')
        self.assertEqual(latest['pendingIssues'][0]['issueId'], 'DF-001')
        third = self.prepare()
        changed = self.issue()
        changed['description'] = 'Additional failing boundary of the same issue'
        self.submit(third, self.result(third, [changed]))
        latest = self.payload()['stages'][0]['rounds'][0]
        self.assertEqual(latest['issues'][0]['changeType'], 'updated')
        self.assertEqual(latest['issues'][0]['id'], 'DF-001')
        self.assertEqual(latest['issues'][0]['originRound'], 1)

    def test_legacy_verified_issue_is_projected_as_compact_verification(self):
        p1 = self.prepare()
        self.submit(p1, self.result(p1, [self.issue()]))
        p2 = self.prepare()
        self.submit(p2, self.result(p2, [self.issue(status='verified')], passed=True))
        latest = self.payload()['stages'][0]['rounds'][0]
        self.assertEqual(latest['issues'], [])
        self.assertEqual(latest['followUps'][0]['result'], 'pass')
        self.assertEqual(latest['stats']['verified'], 1)

    def test_reopened_problem_preserves_id_and_original_history(self):
        p1 = self.prepare()
        self.submit(p1, self.result(p1, [self.issue()]))
        p2 = self.prepare()
        verified = self.result(p2, passed=True)
        verified['verifications'] = [{'issueId': 'DF-001', 'result': 'pass', 'evidence': 'Observed corrected behavior'}]
        self.submit(p2, verified)
        p3 = self.prepare()
        reopened = self.result(p3)
        reopened['verifications'] = [{'issueId': 'DF-001', 'result': 'fail', 'evidence': 'New execution shows recurrence',
                                     'comment': 'Same original defect is reproduced again'}]
        self.submit(p3, reopened)
        stage = self.payload()['stages'][0]
        self.assertEqual(stage['rounds'][0]['issues'][0]['changeType'], 'reopened')
        self.assertEqual(stage['rounds'][0]['issues'][0]['id'], 'DF-001')
        self.assertEqual(stage['rounds'][0]['issues'][0]['originRound'], 1)
        self.assertEqual(stage['pendingIssues'][0]['issueId'], 'DF-001')
        self.assertEqual(stage['rounds'][-1]['issues'][0]['processingStatus'], 'open')

    def test_verification_identity_and_evidence_cannot_be_fabricated_by_omission(self):
        p1 = self.prepare()
        self.submit(p1, self.result(p1, [self.issue()]))
        p2 = self.prepare()
        base = self.result(p2, passed=True)
        invalid = [
            [{'issueId': 'UNKNOWN', 'result': 'pass', 'evidence': 'Not a known issue'}],
            [{'issueId': 'DF-001', 'result': 'pass', 'evidence': ''}],
            [{'issueId': 'DF-001', 'result': 'pass', 'evidence': 'A'},
             {'issueId': 'DF-001', 'result': 'fail', 'evidence': 'B'}],
        ]
        for checks in invalid:
            value = copy.deepcopy(base)
            value['verifications'] = checks
            path = self.root / 'invalid.json'
            path.write_text(json.dumps(value))
            self.run_cli('record', '--stage', 'prd', '--round', 2, '--result', path, ok=False)
        self.assertNotIn('result', ds.database(self.root)['stages']['prd']['rounds'][-1])
        self.assertFalse((self.root / records.round_report_path('prd', 2)).exists())
        base['verifications'] = [{'issueId': 'DF-001', 'result': 'not_checked',
                                  'evidence': 'Actual tool not available'}]
        self.assertNotEqual(self.submit(p2, base)['status'], 'passed')

    def test_fix_requires_evidence_and_does_not_create_a_round_or_close_problem(self):
        p1 = self.prepare()
        self.submit(p1, self.result(p1, [self.issue()]))
        self.prepare(kind='fix', ok=False)
        args = ['reply', '--stage', 'prd', '--round', '1', '--issue', 'DF-001', '--by', 'Owner',
                '--disposition', 'fixed', '--message', 'Applied a concrete fix']
        self.run_cli(*args, ok=False)
        self.run_cli(*args, '--evidence', 'input.md:1; actual fixture change')
        self.assertTrue(self.run_cli(*args, '--evidence', 'input.md:1; actual fixture change')['duplicate'])
        db = ds.database(self.root)
        self.assertEqual(len(db['stages']['prd']['rounds']), 1)
        self.assertEqual(len(db['stages']['prd']['replies']), 1)
        self.assertEqual(self.payload()['stages'][0]['pendingIssues'][0]['status'], 'fixed')
        self.assertNotEqual(self.run_cli('status')['prd']['status'], 'passed')

    def test_pending_context_is_frozen_and_closed_problem_is_not_recopied(self):
        p1 = self.prepare()
        self.submit(p1, self.result(p1, [self.issue()]))
        self.run_cli('reply', '--stage', 'prd', '--round', 1, '--issue', 'DF-001', '--by', 'Owner',
                     '--disposition', 'answered', '--message', 'Clarification needing independent checking')
        p2 = self.prepare()
        request = ds.load(self.root / p2['snapshot'] / 'request.json')
        self.assertEqual(request['priorIssues'][0]['issueId'], 'DF-001')
        self.assertEqual(request['priorIssues'][0]['responses'][0]['disposition'], 'answered')
        value = self.result(p2, passed=True)
        value['verifications'] = [{'issueId': 'DF-001', 'result': 'pass', 'evidence': 'Actually checked clarification'}]
        self.submit(p2, value)
        p3 = self.prepare()
        self.assertEqual(ds.load(self.root / p3['snapshot'] / 'request.json')['priorIssues'], [])

    def test_stock_and_custom_legacy_shell_upgrade_preserves_originals(self):
        p = self.prepare()
        outcome = self.submit(p, self.result(p, [self.issue()]))
        report = self.root / outcome['source']
        frozen = report.read_bytes()
        view = self.root / '验收记录/验收记录总.html'
        old = view.read_text().replace('data-ds-review-template="3"', 'data-legacy-custom="yes"')
        view.write_text(old)
        with patch.object(records, 'LEGACY_SHELL_SHA', ds.digest(records.DATA_BLOCK.sub('<DATA>', old).encode())):
            self.run_cli('status')
        self.assertIn('data-ds-review-template="3"', view.read_text())
        self.assertTrue(any(p.read_text() == old for p in (self.root / records.state_path('页面备份')).glob('*')))
        custom = old.replace('</style>', '/* Customized legacy layout */</style>')
        view.write_text(custom)
        self.run_cli('status', ok=False)
        self.assertEqual(view.read_text(), custom)
        self.run_cli('review-views', '--upgrade-template')
        self.assertIn('data-ds-review-template="3"', view.read_text())
        self.assertTrue(any(p.read_text() == custom for p in (self.root / records.state_path('页面备份')).glob('*')))
        self.assertEqual(report.read_bytes(), frozen)

    def test_script_verification_cannot_close_semantic_historical_problem(self):
        p1 = self.prepare()
        self.submit(p1, self.result(p1, [self.issue()]))
        p2 = self.prepare(method='script', select=False)
        value = self.result(p2, passed=True)
        value['verifications'] = [{'issueId': 'DF-001', 'result': 'pass', 'evidence': 'Only producer scripted check'}]
        path = self.root / 'script-result.json'
        path.write_text(json.dumps(value))
        self.run_cli('record', '--stage', 'prd', '--round', p2['round'], '--result', path, ok=False)
        self.assertNotIn('result', ds.database(self.root)['stages']['prd']['rounds'][-1])


    def test_stale_arrival_cannot_close_an_issue_for_future_rounds(self):
        p1 = self.prepare()
        self.submit(p1, self.result(p1, [self.issue()]))
        p2 = self.prepare()
        (self.root / 'input.md').write_text('Changed while reviewer was checking the previous snapshot')
        value = self.result(p2, passed=True)
        value['verifications'] = [{'issueId': 'DF-001', 'result': 'pass', 'evidence': 'Result refers to obsolete inputs'}]
        self.assertEqual(self.submit(p2, value)['status'], 'stale')
        p3 = self.prepare()
        request = ds.load(self.root / p3['snapshot'] / 'request.json')
        self.assertEqual(request['priorIssues'][0]['issueId'], 'DF-001')
        self.assertNotEqual(self.submit(p3, self.result(p3, passed=True))['status'], 'passed')
        self.assertNotEqual(records.issue_records(ds.database(self.root)['stages']['prd'])[0]['status'], 'verified')

    def test_reopened_round_accepts_reply_and_old_reply_does_not_claim_new_fix(self):
        with patch('ds.now', return_value='2026-11-03T10:00:00+08:00'):
            p1 = self.prepare()
            self.submit(p1, self.result(p1, [self.issue()]))
            self.run_cli('reply', '--stage', 'prd', '--round', 1, '--issue', 'DF-001', '--by', 'Owner',
                         '--disposition', 'fixed', '--message', 'Old fix', '--evidence', 'Old repair evidence')
            p2 = self.prepare()
            close = self.result(p2, passed=True)
            close['verifications'] = [{'issueId': 'DF-001', 'result': 'pass', 'evidence': 'Independent verification'}]
            self.submit(p2, close)
            p3 = self.prepare()
            fail = self.result(p3)
            fail['verifications'] = [{'issueId': 'DF-001', 'result': 'fail', 'evidence': 'Observed recurrence'}]
            self.submit(p3, fail)
            latest = self.payload()['stages'][0]['rounds'][0]['issues'][0]
            self.assertEqual(latest['processingStatus'], 'open')
            self.assertFalse(any(h.get('message') == 'Old fix' for h in latest['history']))
            self.run_cli('reply', '--stage', 'prd', '--round', 3, '--issue', 'DF-001', '--by', 'Owner',
                         '--disposition', 'fixed', '--message', 'New fix for recurrence', '--evidence', 'New repair evidence')
            latest = self.payload()['stages'][0]['rounds'][0]['issues'][0]
            self.assertEqual(latest['processingStatus'], 'fixed')
            self.assertTrue(any(h.get('message') == 'New fix for recurrence' for h in latest['history']))
            self.assertEqual(len(ds.database(self.root)['stages']['prd']['rounds']), 3)

    def test_malformed_result_reports_clear_error_without_partial_result(self):
        p = self.prepare()
        invalid = self.result(p)
        invalid['items'] = [None]
        target = self.root / 'malformed.json'
        target.write_text(json.dumps(invalid))
        response = self.run_cli('record', '--stage', 'prd', '--round', 1, '--result', target, ok=False)
        self.assertIn('逐项', response['error'])
        invalid = self.result(p, [self.issue()])
        invalid['issues'][0]['description'] = {'invalid': 'object'}
        target.write_text(json.dumps(invalid))
        self.run_cli('record', '--stage', 'prd', '--round', 1, '--result', target, ok=False)
        self.assertNotIn('result', ds.database(self.root)['stages']['prd']['rounds'][0])
        invalid = self.result(p)
        invalid['summary'] = {'invalid': 'object'}
        target.write_text(json.dumps(invalid))
        self.run_cli('record', '--stage', 'prd', '--round', 1, '--result', target, ok=False)
        self.assertNotIn('result', ds.database(self.root)['stages']['prd']['rounds'][0])
        self.assertFalse((self.root / records.round_report_path('prd', 1)).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
