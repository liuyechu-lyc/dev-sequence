# 调用与交接示例

以下是给 Agent 的请求示例，不是终端命令。替换项目路径和资料后使用。

## 单阶段

- 需求：使用 `$dev-sequence-requirements`，根据提供的业务想法和反馈梳理需求，只做到需求评审与确认。
- UI：使用 `$dev-sequence-ui`，参考给定 URL、截图、HTML 和项目 `参考素材/`，先确认风格方向，再形成令牌、组件规范和代表性页面。
- 原型：使用 `$dev-sequence-prototype`，根据已有外部 PRD 和设计系统做本期交互原型，不重跑需求与 UI；规则缺口明确列出。
- 技术：使用 `$dev-sequence-tech`，分析当前仓库和需求，形成设计、契约、任务及一致性报告，不写业务代码。
- 代码：使用 `$dev-sequence-code`，按既有需求/方案/任务实施，保留其他改动，记录验证并交独立评审。
- 测试：使用 `$dev-sequence-test`，对指定构建和 AC 实际验收，分别记录 Mock、真实集成与未执行项，不自动发布。

## 组合与全链路

- 使用 `$dev-sequence`，本轮只完成需求、UI和原型，逐阶段确认，到原型为止。
- 使用 `$dev-sequence`，在当前项目完成六阶段；每阶段验收后由我确认。第三方验收时提供完整提示词和资料包，我新开对话交接。
- 使用 `$dev-sequence`，沿用我之前已确认的范围和自动推进授权，从技术方案阶段恢复。先刷新旧验收是否有效，不重做未受影响成果。
- 使用 `$dev-sequence` 完成无UI后台任务，记录UI/原型不适用理由，直接以业务规则、数据和接口验证衔接后续阶段。

## 初始化与验收交接

先将 CORE_ROOT 设置为实际安装的 `dev-sequence` 目录，PROJECT_ROOT 为真实项目目录；它们是示例变量，不依赖固定安装路径。

```sh
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" init --stages proto
```

先交付可阅读成果和自检，再请用户明确选择本模型自动验收、第三方验收或暂不验收。以下命令仅演示用户已实际选择第三方后的登记；所有身份、来源、原文都要替换为真实依据，不能把示例当作授权。

复制所选阶段 `templates/review-request.json` 到项目，填入实际资料路径/版本、范围、清单和复现方法。已有外部说明可映射成多个等价角色，但必须真实覆盖相应职责。

```sh
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" review-choice --stages proto --method third-party --by "实际使用者" --source "本次选择的真实消息位置" --text "实际选择原文"
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" prepare --stage proto --spec "$PROJECT_ROOT/request.json" --method agent
```

执行者把生成的完整提示词输出到对话，连同评审资料目录交给新对话。外部评审者读取冻结内容，填写 `result-template.json` 的副本，不修改快照。回收真实结果后导入：

```sh
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" record --stage proto --round 1 --result "$PROJECT_ROOT/result.json"
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" status
```

确认来自使用者的真实消息或有效预授权后，才用 `confirm --stage proto --by ... --evidence ...` 登记确认。不要从示例复制批准人或伪造消息依据。

## 任务、追溯与原型

```sh
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" tasks --source 技术方案/tasks.json
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" analyze --source 原型/app/prototype.config.json --require taskIds testIds
python3 "$CORE_ROOT/scripts/validate_prototype_v3.py" "$PROJECT_ROOT/原型/app"
python3 "$CORE_ROOT/scripts/build_prototype_v3.py" "$PROJECT_ROOT/原型/app" --output "$PROJECT_ROOT/原型"
python3 "$CORE_ROOT/scripts/validate_prototype_v3.py" "$PROJECT_ROOT/原型/app" --output "$PROJECT_ROOT/原型"
```

任务工具检查依赖和声明证据并生成同源视图；追溯工具检查结构和实际文件引用。它们不代替代码、业务语义和浏览器实测。提前阶段尚无任务/测试映射时不要使用不适用的 `--require`。

## 外部 skill 冲突

允许使用你已有的框架或设计 skill。发现规则差异时要求 Agent 列出双方规则及出处、影响与备选，等你决定；选择记录到本项目规则决策中，不修改外部安装源。

## 本模型自动回传与全自动

- 使用 `$dev-sequence-prototype`，本阶段由本模型在新上下文独立验收，完成后自动回传本对话；原对话依据结果修正和复验，阶段通过后等我确认。
- 使用 `$dev-sequence`，在已经确认的目标和业务范围内全自动执行；授权本模型新上下文验收及回传、原对话修复/复验和阶段自动确认/推进。信息或权限不足、规则冲突时向我说明。

具体授权登记、真实宿主派发、回传和结果消费见共享目录 references/automatic-handoff.md。没有自动授权时不能把“验收完成”当成“允许进入下一阶段”；没有宿主能力时不能假称自动通知。

## 最终测试验收强制新会话

最终测试必须在新会话独立设计并实际执行，不只是审阅原会话报告。结果自动回传原会话修复，更新待测版本后另开全新会话复验；不能复用生产或历史测试上下文。通过需本轮身份、TC、设计/执行证据、构建/环境及证据文件指纹。缺隔离或执行条件时真实标未检查并回传；全自动也不能跳过。

## 同一轮答复与修复

发现、答复和修复留在问题提出轮次。下面命令只追加实际处理，不创建修复轮次，也不自动通过；证据要指向实际修改或检查结果。

```sh
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" reply --stage proto --round 1 --issue "实际问题编号" --by "实际处理者" --disposition fixed --message "实际修改与处理结果" --evidence "实际文件或执行证据"
```

下一次独立复验再创建新review轮次。验收方式选择仅一次时需取得新选择；有明确阶段复用授权时沿用。旧项复验使用结果模板的verifications字段，简要记录编号、pass/fail/not_checked、实际证据和说明，关联回原轮次；已验证关闭且无异常的项不再重复列出。完整流程见[三轮验收示例](acceptance-rounds.md)。
