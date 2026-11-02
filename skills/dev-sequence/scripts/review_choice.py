"""Explicit review-method choices, separate from delivery and automation grants."""
from __future__ import annotations

import copy
import uuid

import ds

LABELS = {'native': '本模型自动验收', 'third-party': '第三方验收', 'skip': '暂不验收'}


def latest(data):
    return (data.get('reviewChoices') or [None])[-1]


def choose(root, args):
    stages = args.stages.split(',')
    if not stages or len(stages) != len(set(stages)) or any(s not in ds.STAGES for s in stages):
        raise ValueError('stages须为不重复的有效阶段ID')
    auth = {'by': args.by, 'source': args.source, 'text': args.text}
    if any(not value.strip() for value in auth.values()):
        raise ValueError('选择须有真实用户、可定位来源和明确选择原文')
    db = ds.database(root)
    if any(s not in db['stages'] for s in stages):
        raise ValueError('请先初始化所选阶段')
    identity = {'method': args.method, 'reuse': args.reuse, 'authorization': auth, 'stages': stages}
    existing = []
    for stage in stages:
        history = db['stages'][stage].get('reviewChoices', [])
        matches = [c for c in history if all(c.get(k) == v for k, v in identity.items())]
        if matches and matches[-1] is not latest(db['stages'][stage]):
            raise ValueError('该选择依据已登记，不能用旧消息重新授权；请提供实际的新选择来源')
        existing.append(matches[-1] if matches else None)
    # A replay cannot replenish a consumed one-round choice.
    if any(existing) and not all(existing):
        raise ValueError('选择记录仅部分存在，请核对登记范围，不覆盖旧授权')
    duplicate = all(existing)
    key = existing[0]['id'] if duplicate else 'RC-' + uuid.uuid4().hex
    if not duplicate:
        at = ds.now()
        for stage in stages:
            db['stages'][stage].setdefault('reviewChoices', []).append(
                dict(copy.deepcopy(identity), id=key, selectedAt=at, preparedRounds=[]))
        ds.refresh(root, db)
        ds.save(root, db)
    return {'choice': key, 'stages': stages, 'method': args.method, 'reuse': args.reuse,
            'duplicate': bool(duplicate), 'status': 'not-reviewed' if args.method == 'skip' else 'selected',
            'note': '只登记实际用户选择；工具不能证明原文真实性。暂不验收不产生通过或豁免。'}


def for_prepare(db, args):
    # Producer fixes and local scripted checks do not dispatch independent reviewers.
    if args.kind == 'fix' or args.method == 'script':
        return None
    choice = latest(ds.stage_data(db, args.stage))
    if not choice:
        raise ValueError('尚未选择验收方式：先交付成果，再请用户选择本模型、第三方或暂不验收；用review-choice登记，不能从完整链路/automation推断')
    if choice['method'] == 'skip':
        raise ValueError('当前选择暂不验收；等待新的明确选择，不创建独立验收轮次')
    if args.method == 'human' and choice['method'] != 'third-party':
        raise ValueError('人工验收须明确选择第三方；不能静默改变本模型选择')
    if choice['reuse'] == 'once' and choice['preparedRounds']:
        raise ValueError('本次验收选择已使用；新轮次须重新选择，或取得明确的阶段复用授权')
    return choice


def bind_round(choice, number):
    if choice is None:
        return None
    choice['preparedRounds'].append(number)
    bound = copy.deepcopy(choice)
    bound['boundRound'] = number
    return bound


def require_native(db, stage, rnd):
    current = latest(ds.stage_data(db, stage))
    bound = rnd.get('reviewChoice')
    if not current or not bound or current['method'] != 'native' or bound['method'] != 'native':
        raise ValueError('缺少本轮明确的本模型验收选择；automation执行授权不能代替方式选择')
    if current['id'] != bound['id'] or rnd['number'] not in current['preparedRounds']:
        raise ValueError('本轮验收方式选择已改变；请按新选择创建新轮次，不复用旧派发')


def add_command(sub):
    p = sub.add_parser('review-choice', help='登记实际用户的验收方式选择，不创建验收通过')
    p.add_argument('--stages', required=True)
    p.add_argument('--method', choices=LABELS, required=True)
    p.add_argument('--reuse', choices=['once', 'stage'], default='once')
    p.add_argument('--by', required=True)
    p.add_argument('--source', required=True)
    p.add_argument('--text', required=True)
