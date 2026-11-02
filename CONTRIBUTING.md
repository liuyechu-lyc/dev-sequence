# Contributing / 参与贡献

Bug reports, documentation improvements, and focused pull requests are welcome.

## Report a problem

Open an issue with the affected skill/stage, package version, host environment, a minimal reproduction, expected/actual behavior, and sanitized evidence. Do not include credentials, private project files, or personal data. For a security vulnerability, follow [SECURITY.md](SECURITY.md).

## Propose a change

1. Describe the user problem and keep the change within that scope.
2. Preserve existing IDs, input compatibility, version-bound acceptance, fresh-context final testing, and authorization boundaries.
3. Update affected English/Chinese documentation and templates together. Keep new guidance focused on decisions the agent actually needs to make.
4. Run the relevant checks below. For behavior changes, include a meaningful regression test and actual results.
5. Open a pull request with the problem, resulting behavior, verification, and any limitations.

```sh
python3 tools/validate_bundle.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=skills/dev-sequence/scripts python3 -m unittest discover -s tests -v
python3 tools/package.py --output dist
```

Packaging refreshes `package-manifest.json`; include the updated manifest when changing packaged files. Generated archives stay in ignored `dist/` and are distributed through releases.

## 中文

欢迎提交问题、改进说明或发起范围明确的 PR。问题反馈请附阶段、版本、环境、复现步骤、预期/实际结果及脱敏证据；不要上传密钥或私有项目资料。行为修改应包含有意义的回归验证，并同步相关中英文说明。打包后提交更新的清单，安装包通过 Releases 分发。

Contributions are provided under the project's [MIT license](LICENSE).
