# Validation / 验证说明

Version: 1.5.0 · 2026-11-11

The published source keeps executable regressions, installation checks, and small examples. Historical development logs, duplicate evidence exports, old reports, and superseded guide assets are excluded.

## Reproduce checks / 复现检查

```sh
python3 tools/validate_bundle.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=skills/dev-sequence/scripts python3 -m unittest discover -s tests -v
python3 tools/package.py --output dist
```

The regression suite covers review choices, round-local responses/repairs, compact historical verification, reopened findings, stale results, independent final-test evidence, interruption recovery, prototype checks, temporary installations, and final delivery gates and packaging. One optional developer check uses Node.js to exercise template scripts in an offline DOM model; runtime tools require only Python 3.10+ standard library. GitHub CI checks Python 3.10 and 3.13.

The 1.4.0 baseline received independent fresh-context behavioral checks with explicitly synthetic data. The 1.4.1 review-gate update passed the same 118-test suite locally and 68 targeted local checks covering template distribution, frozen review inputs, failed/unchecked gate results, evidence fields, applicability records, and preservation of project customizations. These 68 checks are focused maintenance checks, not 68 additional bundled regression tests or an independent business acceptance review.

Checklist coverage, applicability, and evidence semantics still require reviewer judgment. No new Python enforcement of gate IDs was added: if a request omits a gate, the reviewer must report the checklist gap as a blocking issue. These checks validate workflow tools, not a real business project's acceptance, external integration, platform isolation internals, or deployment approval.

## Privacy scope / 隐私检查范围

检查发布目录的全部文件、文件名、图片可见内容及PNG元数据；检查密钥、令牌、密码、个人邮箱、IP/MAC、本机路径和设备标识候选。保留作者已同意公开的GitHub署名、仓库链接及MIT版权名。上传后另外核对新仓库提交元数据与历史隔离。

扫描与人工复核没有发现真实敏感凭证；关键词、合成测试身份、文件指纹和图片资产标识不作为个人账号或设备信息。该结论限于检查范围，不保证未来提交不会引入敏感内容。

历史开发证据在发布目录外保留备份，仓库内不附带个人环境日志。用户真实项目的验收记录由项目自行保管，不随此工具包发布。
