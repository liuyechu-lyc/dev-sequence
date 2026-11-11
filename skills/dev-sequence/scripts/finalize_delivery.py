#!/usr/bin/env python3
"""Promote only reviewed payloads after every declared stage passes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unicodedata
import zipfile
import ds


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def check_gate(project, database):
    declared = project.get('stages', [])
    if not declared or len(set(declared)) != len(declared) or any(s not in ds.STAGES for s in declared):
        raise ValueError('项目必须明确声明本轮适用节点')
    bindings = {}
    for stage in ds.STAGES:
        if stage not in declared:
            continue
        data = database.get('stages', {}).get(stage, {})
        rounds = data.get('rounds', [])
        latest = rounds[-1] if rounds else {}
        confirmation = data.get('confirmation', {})
        if (not isinstance(latest.get('fingerprint'), str) or not latest['fingerprint']
                or latest.get('status') != 'passed' or latest.get('result', {}).get('overall') != 'pass'
                or latest.get('method') not in {'agent', 'human'}
                or confirmation.get('status') != 'accepted'
                or confirmation.get('fingerprint') != latest.get('fingerprint')
                or confirmation.get('round') != latest.get('number')):
            raise ValueError(f'节点 {stage} 尚未在当前指纹上通过并接受，禁止生成最终交付')
        bindings[stage] = {'round': latest['number'], 'fingerprint': latest['fingerprint']}
    if 'test' not in bindings:
        raise ValueError('最终交付必须包含有效最终测试节点；单阶段成果保留在节点目录')
    return bindings


def capture(root, spec, test_round):
    entries = spec.get('artifacts')
    if not isinstance(entries, list) or not entries:
        raise ValueError('最终交付白名单不能为空')
    target_key = lambda name: unicodedata.normalize('NFC', name).casefold()
    targets = {target_key('交付清单.json')}
    payloads = []
    reviewed = test_round.get('snapshotHashes', {})
    for item in entries:
        kind, target = item.get('type'), item.get('target')
        if (kind not in {'file', 'zip-tree'} or not isinstance(target, str)
                or target in {'', '.', '..'} or Path(target).name != target
                or '/' in target or '\\' in target or target.startswith('.')
                or target_key(target) in targets or not str(item.get('purpose', '')).strip()):
            raise ValueError('交付项必须有合法类型、唯一文件名和明确用途')
        targets.add(target_key(target))
        source = ds.inside(root, item.get('source', ''))
        relative = source.relative_to(root)
        if not relative.parts or relative.parts[0] in {'.dev-sequence', '交付', '验收记录'}:
            raise ValueError('交付源必须来自正式成果，不能复制交付自身、过程或验收目录')
        if kind == 'file' and not source.is_file():
            raise ValueError('file源必须是文件')
        if kind == 'zip-tree' and not source.is_dir():
            raise ValueError('zip-tree源必须是文件夹')
        candidates = [source] if kind == 'file' else sorted(source.rglob('*'))
        files = []
        for path in candidates:
            # Ignored development metadata never becomes an implicit payload.
            parts = path.relative_to(source).parts if source.is_dir() else (path.name,)
            if path.is_symlink():
                raise ValueError('交付源不接受符号链接')
            if any(p.startswith('.') or p in {'__pycache__', 'node_modules'} for p in parts):
                continue
            if not path.is_file():
                continue
            raw = path.read_bytes()
            key = 'files/' + path.relative_to(root).as_posix()
            if reviewed.get(key) != sha(raw):
                raise ValueError(f'源文件未被最终测试冻结或已改变: {path.relative_to(root)}')
            files.append((path.relative_to(source).as_posix() if kind == 'zip-tree' else target, raw, key))
        if not files:
            raise ValueError('交付项不能是空文件集合')
        payloads.append({'type': kind, 'target': target, 'source': str(relative), 'purpose': item['purpose'], 'files': files})
    return payloads


def write_payloads(directory, payloads, bindings):
    artifacts = []
    for item in payloads:
        output = directory / item['target']
        if item['type'] == 'file':
            output.write_bytes(item['files'][0][1])
        else:
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, raw, _ in item['files']:
                    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, raw)
        artifacts.append({'file': item['target'], 'source': item['source'], 'purpose': item['purpose'],
                          'sha256': sha(output.read_bytes()),
                          'sourceFiles': [{'path': key.removeprefix('files/'), 'sha256': sha(raw)} for _, raw, key in item['files']]})
    manifest = {'generatedBy': 'dev-sequence/finalize_delivery', 'schemaVersion': 1,
                'stages': bindings, 'artifacts': artifacts}
    (directory / '交付清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def finalize(root, spec):
    output = ds.inside(root, '交付', False)
    with ds.locked(root):
        database = ds.database(root)
        ds.refresh(root, database)
        ds.save(root, database)
        project = ds.load(ds.inside(root, '.dev-sequence/project.json'))
        bindings = check_gate(project, database)
        if output.exists():
            raise ValueError('交付目录已存在；先核对并归档旧版本，禁止合并覆盖')
        test_round = database['stages']['test']['rounds'][-1]
        payloads = capture(root, spec, test_round)
        stage = Path(tempfile.mkdtemp(prefix='final-delivery-', dir=ds.inside(root, '.dev-sequence')))
        try:
            manifest = write_payloads(stage, payloads, bindings)
            # Check source and review validity again immediately before promotion.
            ds.refresh(root, database)
            if check_gate(project, database) != bindings:
                raise ValueError('生成期间节点状态或确认发生变化')
            if capture(root, spec, database['stages']['test']['rounds'][-1]) != payloads:
                raise ValueError('生成期间源文件发生变化')
            ds.save(root, database)
            os.rename(stage, output)
            return {'delivery': str(output), 'files': [a['file'] for a in manifest['artifacts']] + ['交付清单.json'], 'stages': bindings}
        finally:
            if stage.exists():
                shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True)
    args = parser.parse_args()
    try:
        root = args.project.absolute()
        if not root.is_dir() or root.is_symlink() or root.resolve() != root:
            raise ValueError('项目根必须是真实文件夹')
        spec = ds.load(ds.inside(root, args.spec))
        print(json.dumps(finalize(root, spec), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
