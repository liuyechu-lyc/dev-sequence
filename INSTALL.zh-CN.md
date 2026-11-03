# Dev Sequence · 研序 v1.4.0

一套自带工具的研发交付技能：总控＋产品需求规划＋UI设计＋原型设计＋技术方案设计＋代码编写＋测试验收。支持单环节、组合、全链路与中断恢复。名称暂定，后续可统一改名。

本包包含自身所需的全部规范、模板、原型框架和工具。安装与运行不读取旧研发技能，不要求安装 Spec Kit、第三方模型 SDK 或浏览器自动化库。可选外部 skill 仅在用户任务需要时协作，分歧先向使用者说明并询问。

## 内容

- `skills/`：七个可发现 skill，含界面元数据、输入契约、工作流、验收规则、评审入口和模板。
- `skills/dev-sequence/`：本套件共享规则、原型生成器、框架与离线验收 CLI。
- `tools/install.py`：先预览再安装，不覆盖已有同名目录。
- `tools/package.py`：完整源码包包含，可生成完整包及六个带共享运行时的单阶段包，附校验和。
- `tools/validate_bundle.py`：各包均带静态校验；完整源码包另含 `tests/` 行为回归。
- [使用示例](examples/usage.md)、[命令手册](skills/dev-sequence/references/review-protocol.md)、[验证报告](docs/validation.md)。

## 安装

解压后在本包目录运行；将路径换成你的 Agent 实际 skills 目录。先查看计划：

```sh
python3 tools/install.py --dest "$HOME/.codex/skills"
```

确认目标和内容后执行：

```sh
python3 tools/install.py --dest "$HOME/.codex/skills" --apply
```

只安装原型流程及本套件共享运行时：

```sh
python3 tools/install.py --dest "$HOME/.codex/skills" --stages proto --apply
```

单阶段压缩包默认只安装它包含的阶段和共享运行时。所有包都有自己的共享资源，不依赖另一个压缩包。独立运行是直接调用阶段 skill，不要求先执行总控；不要从压缩包只取一个子 skill 目录而漏装随附共享运行时。

已有同名目录时安装器拒绝覆盖；先比较并按实际授权备份/升级。包内默认启用正常自动发现；安装后新开会话或按客户端方式刷新。其他 Agent 可把 skills 中选定目录安装到自己的技能目录，或直接读取相应 SKILL.md，所有资源按相对位置解析。

### 修改源码后的安装与打包

源码清单也校验 README 等说明文件。维护者修改这些文件后，需在项目根目录重新生成清单和安装包，并将更新后的 `package-manifest.json` 与修改一起提交：

```sh
python3 tools/package.py --output dist
python3 -c "import runpy; runpy.run_path('tools/install.py')['verify']()"
```

直接在 GitHub 网页修改 README 后，也需要同步这一步。普通使用者遇到“文件缺失或校验失败”时，先重新下载完整源码或使用已验证的 Release ZIP；维护者确认改动来源后再重建清单。校验失败时不要跳过校验或直接改填预期哈希。仓库文本统一保留 LF 换行，以便不同系统检出后使用同一份文件校验值。

## 使用

完整链路调用 `$dev-sequence`；仅做原型调用 `$dev-sequence-prototype`，其他阶段同理。普通问答不应触发整条流程。只要求方案不授权写业务代码；要求全链路时在已授权范围内持续推进。

默认每阶段独立验收后人工确认。选择本模型验收时，按自动交接协议创建不继承生产历史的新上下文，完成通知自动回到原对话；原对话导入结果并实际修复、复验或推进。明确自动授权且信息/权限充分时自动确认和推进；第三方手动验收仍提供完整提示词。没有宿主能力时明确说明，不能伪造自动化。详见 [自动交接协议](skills/dev-sequence/references/automatic-handoff.md)。

## 文档位置

```text
项目根/
├── 项目理解.md、交互记录.md、工程原则.md
├── 需求/、UI设计/、原型/、技术方案/、代码/、测试验收/
│   └── 每个节点：.review-skill.md + 验收规则.html
└── 验收记录/
    ├── 验收数据.json
    ├── 验收记录.md + .html
    ├── 验收请求-{阶段}-rNNN.md + .html
    ├── 第三方验收提示词-{阶段}-rNNN.md + .html
    ├── 验收报告-{阶段}-rNNN.md + .html + .json
    └── 评审资料-{阶段}-rNNN/
```

实际源码保留仓库原位置。验收记录按「阶段→轮次→问题→结果」同源生成；历史冻结，修复和复验另起轮次。HTML历史视图不能代替 `status` 的当前指纹检查。

## 工具与边界

Python 3.10+，标准库即可运行；无联网操作、付费调用或自动发送。浏览器由执行者使用环境实际可用能力。工具校验内容指纹、结构和声明，不自动证明业务正确、真实外部动作或平台隔离。规则冲突须使用者决策；不把自审视为独立验收。

```sh
python3 skills/dev-sequence/scripts/ds.py --help
python3 tools/validate_bundle.py
```

完整源码包可另外运行全部回归；单阶段包不包含整套测试：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=skills/dev-sequence/scripts python3 -m unittest discover -s tests -v
```

项目业务文档、规则 MD、结构化任务等由实际执行者填写；模板示例不代表已完成或已确认的项目内容。详见各流程入口及共享验收协议。

## 最终测试验收强制新会话

最终测试必须在新会话独立设计并实际执行，不只是审阅原会话报告。结果自动回传原会话修复，更新待测版本后另开全新会话复验；不能复用生产或历史测试上下文。通过需本轮身份、TC、设计/执行证据、构建/环境及证据文件指纹。缺隔离或执行条件时真实标未检查并回传；全自动也不能跳过。
