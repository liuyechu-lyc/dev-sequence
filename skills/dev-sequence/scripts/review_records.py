"""Round-based reading views over immutable review results and appended responses."""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path

STATE_ROOT = Path('.dev-sequence/reviews')
STAGE_FOLDERS = {
    'prd': '需求验收记录', 'ui': 'UI验收记录', 'proto': '原型验收记录',
    'tech': '技术方案验收记录', 'code': '代码验收记录', 'test': '测试验收记录',
}
STATE_LABELS = {
    'pending': '待验收', 'changes-requested': '需修改', 'awaiting-verification': '待复验',
    'passed': '范围内通过', 'stale': '输入已变，待复验', 'waived': '正式豁免',
    'open': '未处理', 'fixed': '已修复，待复验', 'answered': '已答复，待核对',
    'verified': '已验证关闭', 'declined': '不处理（有解释）', 'accepted': '已确认',
    'not_checked': '未检查', 'pass': '复验通过', 'fail': '复验未通过',
}
CHANGE_LABELS = {'new': '新发现', 'updated': '新增问题点', 'reopened': '重新打开'}
KINDS = {'problem': '问题', 'suggestion': '建议', 'question': '疑问'}
DATA_BLOCK = re.compile(r'(<script\s+id="ds-review-data"\s+type="application/json">)([\s\S]*?)(</script>)')
# Exact uncustomized v1.3 shell, with its data block replaced by <DATA>.
LEGACY_SHELL_SHA = 'b8751eaff02c1b361af9ed6dc9d0b38874eec82b1fc80d9070107830e6dae3c0'


def stage_dir(stage):
    return Path('验收记录') / STAGE_FOLDERS[stage]


def round_stem(stage, number):
    return stage_dir(stage) / f'第{number:03d}轮'


def process_dir(stage, number):
    return stage_dir(stage) / '.过程' / f'第{number:03d}轮'


def state_path(name):
    return STATE_ROOT / name


def read_state(root, name, default):
    import ds
    for relative in (state_path(name), Path('验收记录') / name):
        path = ds.inside(root, relative, False)
        if path.is_file():
            return ds.load(path)
    return copy.deepcopy(default)


def round_report_path(stage, number):
    return process_dir(stage, number) / '原始验收报告.json'


def plain(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def line(value):
    return plain(value).replace('|', '｜').replace('\r', '').replace('\n', ' ⏎ ')


def issue_kind(issue):
    return issue.get('kind') or ('suggestion' if issue.get('severity') == 'suggestion' else 'problem')


def timestamp(value):
    try:
        when = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if when.tzinfo is not None:
            return when.timestamp()
    except (ValueError, TypeError, AttributeError):
        pass
    return float('-inf')


def after_review(response, event):
    if 'afterRound' in response:
        return response['afterRound'] >= event['round']
    compared = timestamp(response.get('at')) - timestamp(event.get('at'))
    return compared > 0 or compared == 0 and response['round'] >= event['round']


def result_events(rnd, result):
    at = rnd.get('recordedAt', rnd['createdAt'])
    common = {'round': rnd['number'], 'at': at, 'by': result.get('reviewer', {}).get('name', ''),
              'roundState': rnd['status']}
    valid = rnd.get('resultValidAtRecord', True) and not rnd.get('evidenceInvalid', False)
    for issue in result.get('issues', []):
        status = 'not_checked' if issue['status'] == 'verified' and not valid else issue['status']
        yield issue['id'], dict(common, type='review', status=status, reportedStatus=issue['status'], closureAccepted=valid,
                                message=issue.get('resolution', ''), evidence=issue['evidence'],
                                description=issue['description'], issue=copy.deepcopy(issue))
    for check in result.get('verifications', []):
        status = {'pass': 'verified', 'fail': 'open', 'not_checked': 'not_checked'}[check['result']]
        effective = check['result']
        if check['result'] == 'pass' and not valid:
            status, effective = 'not_checked', 'not_checked'
        yield check['issueId'], dict(common, type='verification', status=status,
                                    result=effective, reportedResult=check['result'], closureAccepted=valid, message=check.get('comment', ''),
                                    evidence=check['evidence'])


def issue_records(stage_data, through=None, incoming=None):
    """Acceptance state follows round number, never callback arrival or producer replies."""
    records = {}
    for rnd in sorted(stage_data.get('rounds', []), key=lambda r: r['number']):
        if through is not None and rnd['number'] > through:
            continue
        result = incoming if incoming is not None and rnd['number'] == through else rnd.get('result', {})
        for key, event in result_events(rnd, result):
            if key not in records:
                if event['type'] != 'review':
                    continue  # Invalid unknown references are rejected before import.
                original = event['issue']
                records[key] = {**copy.deepcopy(original), 'kind': issue_kind(original),
                                'firstRound': rnd['number'], 'reportedStatus': original['status'], 'history': []}
            record = records[key]
            if event['type'] == 'review':
                original = event['issue']
                record.update({k: copy.deepcopy(v) for k, v in original.items() if k != 'history'})
                record['kind'] = issue_kind(original)
            record.update(status=event['status'], latestRound=rnd['number'],
                          latestRoundState=rnd['status'], latestEvent=event)
            record['history'].append(event)
    for response in stage_data.get('replies', []):
        if response['issueId'] in records and (through is None or response['round'] <= through):
            records[response['issueId']]['history'].append({**copy.deepcopy(response), 'type': 'reply'})
    for record in records.values():
        record['history'].sort(key=lambda h: (timestamp(h.get('at')), h.get('round', 0)))
        record['responses'] = [h for h in record['history'] if h['type'] == 'reply']
        record['processingStatus'] = record['status']
        if record['status'] != 'verified':
            after = [h for h in record['responses'] if after_review(h, record['latestEvent'])]
            if after:
                record['processingStatus'] = after[-1]['disposition']
    return list(records.values())


def unresolved_blockers(stage_data, rnd, incoming=None):
    return sorted(i['id'] for i in issue_records(stage_data, rnd['number'], incoming)
                  if i['severity'] in {'critical', 'major'} and i['status'] != 'verified')


def validate_verifications(stage_data, rnd, result):
    checks = result.get('verifications', [])
    if not isinstance(checks, list):
        raise ValueError('verifications必须为数组')
    known = {i['id']: i for i in issue_records(stage_data, rnd['number'] - 1)}
    used = {i['id'] for i in result['issues']}
    for check in checks:
        if (not isinstance(check, dict) or not isinstance(check.get('issueId'), str)
                or not check['issueId'].strip() or check['issueId'] in used):
            raise ValueError('复验编号缺失或重复，不能同时出现在issues和verifications')
        key = check['issueId']
        if key not in known:
            raise ValueError('复验只能引用同阶段更早轮次已提出的问题')
        if check.get('result') not in {'pass', 'fail', 'not_checked'} or not isinstance(check.get('evidence'), str) or not check['evidence'].strip():
            raise ValueError('复验必须包含pass/fail/not_checked及实际证据或未检原因')
        if not isinstance(check.get('comment', ''), str):
            raise ValueError('复验说明须为文本')
        if check['result'] == 'pass' and (rnd['kind'] != 'review' or rnd['method'] == 'script'):
            raise ValueError('生产者处理或脚本检查不能独立关闭历史问题')
        used.add(key)


def review_context(stage_data):
    """Freeze outstanding original findings and factual responses, not a pass claim."""
    return [{'issueId': i['id'], 'originRound': i['firstRound'], 'kind': i['kind'],
             'severity': i['severity'], 'description': i['description'], 'source': i['source'],
             'evidence': i['evidence'], 'status': i['status'], 'responses': copy.deepcopy(i['responses'])}
            for i in issue_records(stage_data) if i['status'] != 'verified']


def source_round(rnd):
    return rnd.get('result', {})


def compact_issue(issue, stage, status=None):
    return {'issueId': issue['id'], 'originRound': issue['firstRound'],
            'status': status or issue.get('processingStatus', issue['status']),
            'severity': issue['severity'], 'originUrl': f'{STAGE_FOLDERS[stage]}/第{issue["firstRound"]:03d}轮.html'}


def round_data(stage, rnd, stage_data, index, jobs):
    result = source_round(rnd)
    before = {i['id']: i for i in issue_records(stage_data, rnd['number'] - 1)}
    at_review = {i['id']: i for i in issue_records(stage_data, rnd['number'])}
    visible, followups = [], []
    for key, event in result_events(rnd, result):
        prior = before.get(key)
        original = event.get('issue')
        change = 'new' if prior is None else None
        if prior and event['status'] == 'open' and prior['status'] == 'verified':
            change = 'reopened'
        elif prior and original and event['status'] not in {'verified', 'fixed', 'answered', 'waived'}:
            if original.get('changeType') in {'updated', 'reopened'}:
                change = original['changeType']
            elif any(original.get(k, issue_kind(original) if k == 'kind' else None) != prior.get(k)
                     for k in ('description', 'severity', 'kind')):
                change = 'updated'
        if change:
            base = copy.deepcopy(original or {k: prior[k] for k in ('id', 'kind', 'severity', 'description', 'source', 'evidence')})
            if original is None:
                base.update(status=event['status'], evidence=event['evidence'], resolution=event['message'])
            current = index[key]
            occurrence = {'round': rnd['number'], 'at': rnd.get('recordedAt', rnd['createdAt'])}
            history = [h for h in current['history'] if h['round'] >= rnd['number']
                       or h['type'] == 'reply' and after_review(h, occurrence)]
            visible.append(dict(base, kind=issue_kind(base), changeType=change, originRound=current['firstRound'], occurrenceRound=rnd['number'],
                                processingStatus=current['processingStatus'], history=copy.deepcopy(history)))
        else:
            if prior and prior['status'] == 'verified' and event['status'] == 'verified':
                continue
            current = at_review[key]
            check_result = event.get('result') or ('pass' if event['status'] == 'verified' else 'not_checked' if event['status'] == 'not_checked' else 'fail')
            comment = event['message']
            if not event.get('closureAccepted', True) and (event.get('reportedResult') == 'pass' or event.get('reportedStatus') == 'verified'):
                comment = '原始结果声称通过，但回传时输入已失效或证据损坏，不计为问题关闭。' + comment
            followups.append(dict(compact_issue(current, stage, event['status']), result=check_result,
                                  evidence=event['evidence'], comment=comment))
    pending = [compact_issue(i, stage, i['status']) for i in at_review.values() if i['status'] != 'verified']
    return {
        'number': rnd['number'], 'kind': rnd['kind'], 'method': rnd['method'],
        'createdAt': rnd['createdAt'], 'recordedAt': rnd.get('recordedAt', ''),
        'status': rnd['status'], 'overall': result.get('overall', 'not_checked'),
        'reviewer': result.get('reviewer', {}), 'scope': rnd['spec']['scope'],
        'reviewChoice': copy.deepcopy(rnd.get('reviewChoice')),
        'fingerprint': rnd['fingerprint'], 'staleReason': rnd.get('staleReason', ''),
        'summary': result.get('summary', '尚未收到验收结果'),
        'validationReasons': rnd.get('validationReasons', []),
        'checks': result.get('items', []), 'notChecked': result.get('notChecked', []),
        'waiver': result.get('waiver'), 'independentTest': result.get('independentTest'),
        'issues': visible, 'followUps': followups, 'pendingIssues': pending,
        'stats': {**{k: sum(i['changeType'] == k for i in visible) for k in CHANGE_LABELS},
                  'verified': sum(i['result'] == 'pass' for i in followups), 'pending': len(pending)},
        'reportUrl': f'{STAGE_FOLDERS[stage]}/第{rnd["number"]:03d}轮.html',
        'auditUrl': f'.过程/第{rnd["number"]:03d}轮/原始验收报告.json' if result and rnd.get('frozenReport') == str(round_report_path(stage, rnd['number'])) else '',
        'handoffs': [{k: job.get(k, '') for k in ('id', 'state', 'reason', 'action', 'reviewerId')}
                     for job in jobs if job['stage'] == stage and job['round'] == rnd['number']],
    }


def display_order(rnd):
    for key in ('recordedAt', 'createdAt'):
        value = timestamp(rnd.get(key))
        if value != float('-inf'):
            return (value, rnd['number'])
    return (float('-inf'), rnd['number'])


def model(root, db):
    import ds
    project_path = ds.inside(root, '.dev-sequence/project.json', False)
    project = ds.load(project_path).get('name', root.name) if project_path.exists() else root.name
    jobs = list(read_state(root, '交接数据.json', {'jobs': {}}).get('jobs', {}).values())
    payload = {'schemaVersion': 3, 'mode': 'summary', 'project': project, 'stages': []}
    for stage in ds.STAGES:
        if stage not in db['stages']:
            continue
        data = db['stages'][stage]
        index = {i['id']: i for i in issue_records(data)}
        rounds = sorted(data['rounds'], key=display_order, reverse=True)
        current = max(data['rounds'], key=lambda r: r['number'], default=None)
        payload['stages'].append({
            'id': stage, 'name': ds.STAGES[stage][0], 'folder': STAGE_FOLDERS[stage],
            'status': current['status'] if current else 'pending',
            'confirmation': copy.deepcopy(data['confirmation']),
            'pendingIssues': [compact_issue(i, stage) for i in index.values() if i['status'] != 'verified'],
            'reviewChoice': copy.deepcopy((data.get('reviewChoices') or [None])[-1]),
            'rounds': [round_data(stage, rnd, data, index, jobs) for rnd in rounds],
        })
    return payload


def issue_md(issue, heading=3):
    md = '\n' + '#' * heading + f" {issue['id']} · {KINDS[issue['kind']]} · {CHANGE_LABELS[issue['changeType']]}\n\n"
    md += f"{issue['description']}\n\n严重度：{line(issue['severity'])}；验收时状态：{STATE_LABELS.get(issue['status'], issue['status'])}；后续处理：{STATE_LABELS.get(issue['processingStatus'], issue['processingStatus'])}。\n\n"
    md += f"来源：{line(issue['source'])}\n\n证据：{line(issue['evidence'])}\n\n"
    if issue.get('resolution'):
        md += f"原始建议或本次变化说明：{line(issue['resolution'])}\n\n"
    md += '**答复、修复与后续复验**\n\n'
    history = issue.get('history', [])
    useful = [h for h in history if h['type'] != 'review' or h.get('status') != 'open' or h['round'] != issue['occurrenceRound']]
    if not useful:
        return md + '暂无处理答复；不能据此认定已解决。\n'
    md += '| 时间 | 来源轮次 | 主体 | 处理/答复 | 说明与依据 |\n|---|---|---|---|---|\n'
    for h in useful:
        action = h.get('disposition', h.get('status', ''))
        message = h.get('message') or h.get('description', '')
        if h.get('type') == 'review' and h.get('description') and h.get('message'):
            message = h['description'] + '；说明：' + h['message']
        if not h.get('closureAccepted', True) and h.get('status') == 'not_checked':
            message += '；输入失效或证据损坏，不能计为验证关闭。'
        if h.get('evidence'):
            message += '；依据：' + plain(h['evidence'])
        md += '| ' + ' | '.join(line(x) for x in (h.get('at', ''), h.get('round', ''), h.get('by', ''), STATE_LABELS.get(action, action), message)) + ' |\n'
    return md


def round_md(stage, rnd, heading=2, summary=False):
    title = f"{'历史修复记录' if rnd['kind'] == 'fix' else '验收记录'} 第{rnd['number']:03d}轮"
    md = '\n' + '#' * heading + ' ' + title + '\n\n'
    md += '| 轮次信息 | 内容 |\n|---|---|\n'
    for key, value in [('创建时间', rnd['createdAt']), ('结果记录时间', rnd['recordedAt'] or '待回传'),
                       ('评审方式', rnd['method']), ('当前有效状态', STATE_LABELS.get(rnd['status'], rnd['status'])),
                       ('原始结论', rnd['overall']), ('评审者', rnd['reviewer']),
                       ('输入指纹', rnd['fingerprint']), ('声明范围', rnd['scope']['description'])]:
        md += f'| {key} | {line(value)} |\n'
    s = rnd['stats']
    md += f"\n本轮：新发现 {s['new']}；新增问题点 {s['updated']}；重新打开 {s['reopened']}；复验关闭 {s['verified']}；验收当时未关闭 {s['pending']}。\n"
    md += '\n' + rnd['summary'] + '\n'
    if summary:
        md += f"\n[查看本轮独立记录]({stage['folder']}/第{rnd['number']:03d}轮.md)\n"
    if rnd.get('reviewChoice'):
        md += '\n本轮验收方式选择及依据：' + line(rnd['reviewChoice']) + '\n'
    md += '\n' + '#' * (heading + 1) + ' 本轮新发现与变化\n'
    if not rnd['issues']:
        md += '\n尚未收到验收结果。\n' if not rnd['recordedAt'] else '\n本轮没有新增或重新打开的问题；历史项见复验结果和待处理提示。\n'
    for issue in rnd['issues']:
        md += issue_md(issue, heading + 2)
    if rnd['followUps']:
        md += '\n' + '#' * (heading + 1) + ' 历史问题复验\n\n| 问题 | 提出轮次 | 本次结论 | 证据与说明 |\n|---|---|---|---|\n'
        for check in rnd['followUps']:
            link = f"{'' if summary else '../'}{stage['folder']}/第{check['originRound']:03d}轮.md"
            md += f"| [{line(check['issueId'])}]({link}) | 第{check['originRound']:03d}轮 | {STATE_LABELS[check['result']]} | {line(check['evidence'])}；{line(check['comment'])} |\n"
    if rnd['pendingIssues']:
        md += '\n验收当时未关闭（编号及原轮次）：' + '、'.join(f"{line(i['issueId'])}（第{i['originRound']:03d}轮）" for i in rnd['pendingIssues']) + '。\n'
    md += '\n' + '#' * (heading + 1) + ' 逐项检查\n\n| 检查项 | 结论 | 证据 | 说明 |\n|---|---|---|---|\n'
    for check in rnd['checks']:
        md += '| ' + ' | '.join(line(check.get(k, '')) for k in ('id', 'result', 'evidence', 'comment')) + ' |\n'
    md += f"\n未检查：{line(rnd['notChecked'])}\n\n明确排除：{line(rnd['scope']['exclusions'])}\n"
    for label, value in [('尚未关闭的历史阻断项', rnd.get('validationReasons', [])), ('失效原因', rnd['staleReason']), ('正式豁免', rnd['waiver']), ('独立测试设计与执行', rnd['independentTest']), ('交接状态', rnd['handoffs'])]:
        if value:
            md += f'\n{label}：{line(value)}\n'
    if rnd['auditUrl']:
        prefix = stage['folder'] + '/' if summary else ''
        md += f"\n[冻结原始结果]({prefix}{rnd['auditUrl']})\n"
    return md


def detail_md(project, stage, rnd):
    title = stage['name'] + ('记录' if stage['name'].endswith('验收') else '验收记录')
    return (f"# {title} 第{rnd['number']:03d}轮\n\n项目：{line(project)}\n"
            + round_md(stage, rnd)
            + '\n原始结论冻结保留；答复、修复与后续复验追加，不改写原始发现。\n')


def summary_md(payload):
    md = f"# {payload['project']} 验收记录总览\n\n按阶段和轮次阅读；答复与修复留在问题提出轮次，历史复验简要关联，已关闭项不重复列为新发现。\n"
    for stage in payload['stages']:
        confirmation = stage['confirmation']
        label = {'pending': '待确认', 'accepted': '已确认', 'changes-requested': '要求调整', 'stale': '确认已失效'}.get(confirmation.get('status'), '待确认')
        md += f"\n## {stage['name']}\n\n当前验收：{STATE_LABELS.get(stage['status'], stage['status'])}；阶段确认：{label}。\n"
        choice = stage.get('reviewChoice')
        if choice:
            from review_choice import LABELS
            md += '\n当前验收方式选择：' + LABELS[choice['method']] + '；复用范围：' + ('仅一次' if choice['reuse'] == 'once' else '本阶段') + '。\n'
            md += '\n选择依据：' + line(choice['authorization']) + '\n'
            if choice['method'] == 'skip':
                md += '\n当前选择暂不验收；不产生通过或豁免。\n'
        else:
            md += '\n验收方式尚未登记；不得推断为本模型。\n'
        if confirmation.get('by'):
            md += f"\n确认人：{line(confirmation['by'])}；依据：{line(confirmation.get('evidence', ''))}。\n"
        if stage['pendingIssues']:
            md += '\n当前待处理：' + '、'.join(f"{line(i['issueId'])}（{STATE_LABELS.get(i['status'], i['status'])}，第{i['originRound']:03d}轮）" for i in stage['pendingIssues']) + '。\n'
        md += '\n轮次按结果记录时间倒序；未回传按创建时间，同一时刻按轮次号倒序。\n'
        if not stage['rounds']:
            md += '\n暂无验收轮次。\n'
        for rnd in stage['rounds']:
            md += round_md(stage, rnd, 3, summary=True)
    return md


def backup_shell(root, relative, content):
    import ds
    backup = state_path('页面备份') / (ds.digest(content.encode())[:16] + '-' + Path(relative).name)
    path = ds.inside(root, backup, False)
    if not path.exists():
        ds.write(path, content, True)
    elif path.read_text(encoding='utf-8') != content:
        raise ValueError('页面备份内容冲突，拒绝覆盖')
    return backup


def update_html(root, relative, payload, upgrade=False):
    import ds
    path = ds.inside(root, relative, False)
    template = (ds.CORE / 'assets/review-record.html').read_text(encoding='utf-8')
    content = path.read_text(encoding='utf-8') if path.exists() else template
    matches = list(DATA_BLOCK.finditer(content))
    current_shell = 'data-ds-review-template="3"' in content
    if not current_shell:
        stock = ds.digest(DATA_BLOCK.sub('<DATA>', content).encode()) == LEGACY_SHELL_SHA
        if not (upgrade or stock):
            raise ValueError('旧版或自定义验收页面需显式升级：review-views --upgrade-template；升级会备份旧页面再采用新版模板')
        backup_shell(root, relative, content)
        content = template
        matches = list(DATA_BLOCK.finditer(content))
    elif upgrade:
        backup_shell(root, relative, content)
        content = template
        matches = list(DATA_BLOCK.finditer(content))
    if len(matches) != 1:
        raise ValueError(f'验收HTML缺少唯一ds-review-data数据块，拒绝覆盖页面框架: {relative}')
    data = ds.canonical(payload).replace('<', '\\u003c')
    updated = DATA_BLOCK.sub(lambda m: m[1] + '\n' + data + '\n' + m[3], content, count=1)
    if updated != content:
        ds.write(path, updated)


def save_views(root, db, upgrade=False):
    import ds
    payload = model(root, db)
    # Render HTML first so an incompatible custom shell does not silently replace its MD.
    update_html(root, '验收记录/验收记录总.html', payload, upgrade)
    ds.write(ds.inside(root, '验收记录/验收记录总.md', False), summary_md(payload))
    for stage in payload['stages']:
        ds.inside(root, stage_dir(stage['id']), False).mkdir(parents=True, exist_ok=True)
        for rnd in stage['rounds']:
            stem = round_stem(stage['id'], rnd['number'])
            detail = {'schemaVersion': 3, 'mode': 'round', 'project': payload['project'],
                      'stages': [{**stage, 'rounds': [rnd]}]}
            update_html(root, str(stem) + '.html', detail, upgrade)
            ds.write(ds.inside(root, str(stem) + '.md', False), detail_md(payload['project'], stage, rnd))


def rebuild(root, args):
    import ds
    db = ds.database(root)
    ds.refresh(root, db)
    save_views(root, db, args.upgrade_template)
    ds.save(root, db)
    return {'status': 'views-updated', 'layoutVersion': 3, 'upgradedTemplate': args.upgrade_template,
            'note': '只刷新阅读视图和当前有效性；不改写冻结报告，不合并或重编号旧轮次。'}


def reply(root, args):
    import ds
    db = ds.database(root)
    ds.refresh(root, db)
    data = ds.stage_data(db, args.stage)
    rnd = next((r for r in data['rounds'] if r['number'] == args.round), None)
    index = {i['id']: i for i in issue_records(data)}
    visible = round_data(args.stage, rnd, data, index, [])['issues'] if rnd else []
    if not rnd or not (any(i['id'] == args.issue for i in rnd.get('result', {}).get('issues', []))
                       or any(i['id'] == args.issue for i in visible)):
        raise ValueError('本轮没有提出该问题，请向问题提出的轮次追加答复')
    if not args.by.strip() or not args.message.strip():
        raise ValueError('答复须有真实主体与处理结果或不处理的解释')
    if args.disposition == 'fixed' and not (args.evidence or '').strip():
        raise ValueError('修复答复须有实际修改或验证依据，不能仅声明已修复')
    event = {'issueId': args.issue, 'round': args.round, 'by': args.by, 'message': args.message,
             'disposition': args.disposition, 'evidence': args.evidence or '', 'at': ds.now(),
             'afterRound': max((r['number'] for r in data['rounds'] if r.get('result')), default=args.round)}
    previous = data.setdefault('replies', [])
    keys = ('issueId', 'round', 'by', 'message', 'disposition', 'evidence')
    if any(all(old.get(key) == event[key] for key in keys) for old in previous):
        ds.save(root, db)
        return {'stage': args.stage, 'round': args.round, 'issue': args.issue, 'duplicate': True,
                'status': rnd['status'], 'note': '相同答复已登记，不重复追加'}
    previous.append(event)
    ds.save(root, db)
    return {'stage': args.stage, 'round': args.round, 'issue': args.issue,
            'reply': event, 'status': rnd['status'], 'note': '答复和修复追加在本轮，不增加轮次；独立复验后才能关闭问题。'}
