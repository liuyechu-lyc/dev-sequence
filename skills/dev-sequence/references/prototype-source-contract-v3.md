# 原型源数据与构建协议 v3

## 目录

1. 目标与边界
2. 源目录与交付目录
3. 项目注册表
4. 技术规范与稳定锚点
5. 变更影响
6. 构建与版本
7. 校验与验收
8. Index 与页面交互模式
9. 新迭代重置

## 1. 目标与边界

本契约中的资源均相对本套件 CORE_ROOT 解析。验收规则放节点根，验收报告按阶段与轮次放项目根验收记录/原型验收记录/；请求/提示词放本轮.过程/，按review-protocol.md和review-layout.md生成一对单轮MD/HTML及同源总览。默认原型节点为原型/；下文原型-v3/仅为示例目录。

- 只维护业务功能页、控件说明页、图解说明页、项目数据和技术规范；禁止在项目中重写 Index 框架与标注运行时。
- 项目注册表是页面、导航、项目概述和终端声明的唯一数据源。
- 技术规范与业务 DOM 分文件维护，仅以稳定模块 key 建立关联。
- 构建产物必须是可通过 `file://` 打开的独立 HTML，不依赖 `app/`、服务端或外部 CDN。
- 框架、通信、规范渲染是低自由度；业务 DOM 与页面交互保持中高自由度。禁止将所有业务页面强制改造成通用 JSON 页面生成器。

## 2. 源目录与交付目录

```text
原型-v3/
├── app/
│   ├── prototype.config.json
│   ├── pages/                 # 完整业务/控件说明/图解说明 HTML；不含原型框架
│   └── specs/                 # 页面级、模块级技术规范
├── index.html                 # 构建产物
├── overview.html              # 构建产物
└── *.html                     # 构建产物
```

`app/` 只用于维护和生成；交付目录内的 HTML 不得读取 `app/`。业务页面、控件说明页和图解说明页可以由原生 HTML、React、Vue 或其他工具先生成成完整 HTML，再交给构建器装配框架。

### 2.1 生成器与生成产物

原型流程分为三类责任层：

| 层级 | 唯一职责 |
|---|---|
| 生成器 | 在 Skill 的 `assets/prototype-framework/` 与构建脚本中维护 Index DOM/CSS/JS、页面公共运行时、通信、规范装配、版本和校验 |
| 项目源数据 | 在 `app/prototype.config.json`、`app/pages/`、`app/specs/` 中维护项目声明、业务/控件说明/图解说明页面和技术规范 |
| 生成产物 | 由生成器输出 `index.html`、`overview.html` 和各业务 HTML；只用于查看与交付，不反向作为维护源 |

框架行为由 Skill/本契约定义，代码实现由生成器模板负责。兼容终端、Manifest、公共 JS/CSS 引用或内嵌、标注层和通信字段均不得由业务页面手写。

项目概述采用固定的三层维护结构：内容数据只存在于 `prototype.config.json.overview` 与页面注册表；DOM 壳只存在于 `assets/prototype-framework/overview-template.html`；视觉样式只存在于 `assets/prototype-framework/overview.css`。构建脚本只负责结构化校验、派生统计、生成重复行和填充模板，不得重新内嵌整页 DOM 或 CSS。生成的 `overview.html` 仅为交付产物，不是维护源。

生成器必须将同一版本的公共 JS/CSS 内嵌到每个最终 HTML。生成产物中的代码重复属于编译结果，不代表多份维护源；借此保持每个 HTML 可独立通过 `file://` 打开且不依赖 `app/`、公共资源目录、服务端或 CDN。为避免部署后 Index 读取旧子页面，构建器还必须统一计算项目 `buildId`，并由 Index 仅在 iframe 请求上附加该版本参数。

当多个页面共享同一 SPA bundle、每个输出文件只通过路由选择页面时，在项目注册表声明 `"sourceMode": "shared-spa-bundle"`。此模式仍要求当前页面的全部规范 key 在 bundle 中存在，但允许 bundle 同时包含其他页面锚点；交付前必须通过浏览器逐页验证实际可见锚点不存在重复或孤立。

## 3. 项目注册表

`prototype.config.json` 使用 `schemaVersion: 3`，页面注册表必须集中维护：

- 稳定 `id`、英文输出文件名、标题。
- 页面类型：项目概述使用 `kind: "overview"`，业务功能页可省略 `kind`，控件说明页使用 `kind: "component-guide"`，图解说明页使用 `kind: "diagram-guide"`。
- 导航分组与业务端。
- 页面长期功能描述与本版本修改点。
- 新项目声明 `contentStandardVersion: 1`，并按下文绑定业务版本、需求追溯及演示说明。
- `changeType`、`changeImpact`。
- 页面支持终端和默认终端。
- 业务 HTML 与独立规范文件路径。

`overview` 同时维护概述页的内容数据：

- `summary`、`goals`、`rules`：项目概述、目标与关键规则。`rules` 每项使用非空 `title` 与 `content`；概述页按一行一列渲染规则，每条规则先显示标题并换行，再显示描述，不把多条规则并排为多列。
- `glossary`：名词解析数组，每项使用唯一 `term` 与非空 `definition`。
- `changeLogOrder`：固定为 `newest-first`，明确修改记录按最新批次在前展示。
- `prototypeChangeLog`：原型修改记录数组。每项代表表格中的一行，包含 `version`、`datetime`（`YYYY-MM-DD HH:mm`）、`terminal`、`pages`、`modules` 和 `summary`。`version` 使用 `V{major}.{minor}`；迭代的最早确认批次必须为 `V1.0`，后续批次默认递增次版本，作者可明确指定新的大版本。同一版本批次必须共用一个日期时间。
- `terminal` 记录页面所属业务端（如“配置&管理端”“骑手端”“项目文档”）。`pages` 与 `modules` 为保持引用结构统一仍使用数组，但每项必须且只能包含一个引用；页面与模块引用使用 `name` 和 `action`，`action` 仅允许“新增、修改、删除”。以“版本 + 日期时间 + 终端 + 页面 + 模块”为一行粒度，同一批次涉及多个页面或模块时拆为多项，每项 `summary` 只描述当前模块的修改内容。
- 源数组必须按版本倒序排列，最新批次整体插入数组最前方；生成器严格按数组原序渲染，不得二次排序。同一版本、日期时间、终端的行必须连续排列。生成器按层级对连续相同的版本、日期时间、终端分别生成 `rowspan`；页面/模块名称与操作标签上下两行展示，操作标签不得与名称同行，表格剩余宽度优先分配给修改内容概述。
- `faq`：研发/测试疑问数组。每项包含唯一 `id`、`raisedAt`、`role`、`scope`、`question`、`answer`、`status`；角色仅允许研发、测试，状态仅允许待确认、已答复、已关闭。
- `tracking`：埋点文档 URL 或无需埋点声明。
- `demo`：模拟范围、演示路径、失败触发、业务数据重置及刷新/切页后的保留规则，结构见下文。

原型修改记录是作者控制的数据，不是文件差异日志。只有作者明确要求写入某次调整时才追加；禁止自动把零碎修复、同一细节的反复调整或构建产物变化写成多条。记录在当前迭代内增量保留，执行新迭代重置或开始新项目时清空。FAQ 按研发、测试实际提问增量维护，不用原型评审问题自动代替。

Index 导航、项目概述分端表格及统计、页面基础 manifest 均由构建器生成，禁止在其他文件重复维护。项目概述中的“项目涉及页面”即项目页面目录，业务页面不得再生成独立目录页、返回目录按钮或重复页面卡片入口。

控件说明页是项目概述页、业务功能页之外的第三类页面。它使用独立“原型控件说明”导航分组，
在项目概述单独成组统计，不计入任何实际业务端页面数量。控件说明页不声明技术规范，
页面本身以结构说明、字段规则和一维/二维/分组枚举承载详细要求。完整边界和中性模块见
`references/prototype-component-guide-standard.md`。

图解说明页是第四类页面。它使用独立项目图解导航分组，在项目概述单独成组统计，
不计入任何实际业务端页面数量。它默认不声明技术规范、不生成红蓝标注，页面正文本身是流程、架构、
时序、状态或对应关系的单一说明源。完整边界与中性骨架见 `references/prototype-diagram-guide-standard.md`。

页面级技术规范的第一项固定为“兼容终端”，由构建器根据页面 `viewports.supported` 和 `viewports.default` 自动生成，展示终端类型、基准尺寸和默认终端。规范 JSON 禁止重复维护 `supported-viewports`，避免终端声明出现双数据源。

### 3.1 业务版本与 PRD 绑定

新项目在配置顶层使用 `contentStandardVersion: 1`。这表示启用以下内容完整性检查；原有 `schemaVersion: 3`、通信版本及规范 Schema 5 保持其原职责。

```json
{
  "contentStandardVersion": 1,
  "project": {
    "name": "项目名称",
    "version": "v0.1",
    "prd": { "path": "../../需求/需求.md", "version": "v0.1" }
  }
}
```

- `project.version` 是原型的业务版本；`project.prd.path` 相对 `app/` 解析，`project.prd.version` 指向本原型依据的 PRD 业务版本。PRD 与原型可以采用不同版本号，必须明确对应关系。
- PRD 的“文档信息”使用 `| 当前版本 | v0.1 |` 表格行。为兼容旧文档，也识别“版本”表格行或 `版本：v0.1` 文本。版本比较忽略英文字母大小写，不自动升级或覆盖作者版本。
- 构建时读取 PRD，核对当前版本并记录内容 SHA-256；业务版本和绑定状态在概述展示，`businessBinding` 随每个页面 manifest 内嵌。最终 HTML 不在运行时读取 PRD。
- `frameworkVersion` 和 `buildId` 继续分别代表框架版本与构建输入，不替代业务版本。绑定 PRD 内容也进入确定性 `buildId`；PRD 或配置变化后旧产物需重建。
- 未声明 `contentStandardVersion` 的旧 v3 项目仍可结构校验，但必须输出迁移/未检查警告，不能声称完整需求覆盖。`--strict-content` 可提前检查迁移缺口。新标准项目缺少绑定、PRD 不可读、版本不一致时不得按完整内容校验通过。

### 3.2 需求追溯的单一来源

保留已有 `US/FR/PG/FL/FD/AC` 编号；公共规则使用项目已有编号（例如 `BR-001`），不为字母形式统一而重编号。尚无原型时由 PRD 附录维护追溯；进入原型阶段后，将其转换为配置顶层 `traceability` 并作为唯一结构化维护源，概述由其生成，PRD 附录引用该映射或由它生成，不手工维护第二份完整副本。

```json
"traceability": [
  {
    "requirementId": "FR-001",
    "ruleIds": ["BR-001"],
    "prdPageId": "PG-001",
    "pageId": "example-list",
    "moduleKey": "batch-actions",
    "scenario": "批量操作成功、失败与恢复",
    "acceptanceIds": ["AC-001"],
    "coverage": "partial",
    "notes": "失败后的重试仍需补充演示。"
  }
]
```

- `requirementId`、`scenario`、非空 `acceptanceIds` 和 `coverage` 必填；`ruleIds` 可为空。`prdPageId` 可选，用于保留 PRD 的 PG 编号；`pageId` 使用注册表既有稳定 id，`moduleKey` 按需定位规范模块。
- 一条需求可多行映射不同页面或状态；一个页面也可关联多条需求。`coverage` 为 `covered`、`partial`、`pending` 或 `not-applicable`，表示设计覆盖，不表示开发完成或测试通过。
- 无界面需求明确写 `"pageId": null`，并提供非空 `reason`、`evidence`（业务规则、集成或真实结果验证说明的引用），不虚构页面；仍需关联验收 ID。
- 脚本核对映射中的页面、模块及 PRD 已定义的需求/规则/验收编号。可识别标题、表格首列或 `FR-001：...` 形式的编号定义；代码围栏内的模板样例不算真实定义。采用其他文档格式时先补可识别的定义或人工核对，不把未检查当通过。
- 脚本不判断场景是否真的可触发，也不自动判断范围外需求是否应纳入。评审须按本期范围核对覆盖完整性，并检查每行的真实交互与业务结果。

### 3.3 演示与模拟边界

```json
"demo": {
  "scope": "说明哪些是假数据、模拟操作、真实能力及未覆盖内容。",
  "paths": [{ "name": "主流程", "pageIds": ["example-list"], "steps": ["进入页面", "执行操作并观察结果"] }],
  "failureTriggers": ["说明如何可重复地触发关键失败状态。"],
  "reset": "说明恢复初始演示数据的方法。",
  "persistence": "说明刷新、切页、角色切换后的数据保留范围。"
}
```

该对象位于 `overview.demo`，由概述统一展示。`paths` 至少一条；`failureTriggers` 无适用情况时可为空，但必须增加 `failureNotApplicableReason`。演示路径涉及的 `pageIds` 必须存在。

按实际复杂度提供角色/场景切换、失败触发及重置，不强制所有项目制作固定工具面板。这里的业务数据重置不同于新迭代的红蓝标注重置。需求编号、评审标注与演示工具保持在评审层，可隐藏，不混入产品正式界面。

模拟交互不能证明后台授权、真实集成、性能或模型质量。产品包含 AI 功能时，按 PRD 的 AI 章节补充生成中、澄清、无依据、等待确认、工具失败和人工接管等实际适用状态；普通软件不启用 AI 专属要求。

### 3.4 业务规则与页面说明的职责

PRD 维护业务定义、权限、计算口径和验收条件；原型维护页面结构与具体交互呈现；技术方案维护实现决策。概述 `rules` 及模块说明展示摘要并注明 PRD 规则编号/位置，避免独立定义第二套规则。发现冲突须记录并同步修正，不能以“最后修改文件”自动决定口径。

页面级规范按需覆盖角色、用户任务、入口/前置条件、数据范围/排序/分页、离开/未保存处理和恢复方式。复杂控件继续通过控件说明页复用；简单标准控件可引用公共约定，仅补差异。

## 4. 技术规范与稳定锚点

规范文件结构：

```json
{
  "enabled": true,
  "page": {
    "title": "页面技术规范",
    "sections": []
  },
  "modules": [
    {
      "key": "search",
      "title": "搜索模块",
      "layer": "base",
      "changeType": "modified",
      "changeImpact": "interaction",
      "sections": []
    }
  ]
}
```

业务技术规范区块可以引用控件说明页，引用对象只保存稳定 `pageId`；`references`
只能声明在具有 `key`、`title` 的规范 section 上：

```json
{
  "key": "component-guide-reference",
  "title": "控件详细规则",
  "content": "本模块只维护页面和列表规则；控件字段与状态由引用页面统一维护。",
  "references": [{ "pageId": "example-component-guide" }],
  "changeType": "modified"
}
```

Index 根据注册表解析页面标题并生成可点击跳转。目标必须存在、不得是当前页面，且必须使用
`kind: "component-guide"`。引用不新增 iframe 通信消息；页面切换仍由 Index 完成并重置画布位置。

业务 DOM 只声明同名锚点：

```html
<section data-ds-spec-anchor="search">...</section>
```

每个模块必须且只能包含一份 `type: "controls"` 的结构化“内容与控件说明”：

```json
{
  "key": "controls",
  "title": "内容与控件说明",
  "type": "controls",
  "items": [
    {
      "name": "站点名称",
      "controlType": "单选",
      "dataSource": "配送站点接口",
      "defaultValue": "当前账号所属站点",
      "required": true,
      "options": "接口返回的可用站点",
      "constraints": "仅允许选择一个站点",
      "changeType": "existing"
    }
  ]
}
```

控件说明规则：

- 文本、标签、只读字段等文本类内容必须写明数据来源，包括固定规则/文案、配置项、接口字段、计算结果或上游系统。
- 单行文本、多行文本必须写明 `defaultValue`、布尔值 `required` 和 `constraints`；无默认值也必须明确写“无”。
- 单选、多选、单选组、多选组必须写明 `defaultValue`、布尔值 `required` 和 `options`，并在数据源中区分固定枚举或外部数据。
- Tab 必须写明 `defaultValue`。
- 日期、时间、日期段、时间段必须写明 `defaultValue` 和 `selectableRange`。
- 保存/提交类按钮使用 `buttonRole: "save-submit"`。`validationRules` 描述校验项目；`failureResult` 描述校验失败的阻断和提示；`successResult` 描述提交真正成功后的数据、关闭/跳转/刷新结果。
- 保存/提交控件的现有 `note` 字段说明提交生命周期：提交中状态、业务/网络失败、超时、输入保留、取消/重试及重复提交策略；不适用情况说明原因。`contentStandardVersion: 1` 要求非空 `note`，旧项目缺少时给出警告。字段齐全不代表这些场景已实现，须实际触发验证。
- 普通操作按钮使用 `buttonRole: "action"`，并写明 `actionResult`，明确点击后打开的弹窗/抽屉、跳转页面、关闭载体、数据刷新或状态变化；禁止使用“执行操作”等不可验收描述。
- 模块内其他可见链接、状态、表格、图片、图标和分页也必须进入清单；可在 `constraints` 或 `note` 中描述字段集合、触发行为和展示条件。

规则：

- 禁止在规范内保存 CSS `target`、DOM 路径、显示编号或单独的 markers 数组。
- 模块 `key` 在页面内唯一且稳定；排序和 DOM 内部重构不得改变 key。
- 每个规范模块必须对应一个可见锚点；同一时刻最多渲染一个同名锚点。
- 页面内部 DOM 可自由调整，只要模块职责不变且稳定锚点保留，就不需要修改规范。
- 弹窗、抽屉及其他浮层模块使用 `layer: "modal"`；锚点必须位于随载体显示/隐藏的容器内部。每个会承载标注或阻断下层操作的载体根节点必须声明 `data-ds-overlay-root`。
- 标注生成阶段只创建标注、编号、状态、点击事件和锚点关联，不保存绝对定位坐标。公共页面运行时必须在首次挂载、终端切换、滚动、尺寸变化及弹窗/抽屉布局变化时重新计算坐标。
- 标注默认以锚点右上角为中心；仅当标注超出 iframe 可视边界时执行边界内收。标注外径固定为 24px（包含 2px 边框），边缘保留 2px 安全距离；未越界标注不得改变原定位。
- 标注层级由公共运行时根据当前可见的 `data-ds-overlay-root` 动态派生，不在规范 JSON 或业务 DOM 保存数字深度。固定层序为“基础页面 < 基础页面标注 < 一级载体 < 一级载体内标注 < 二级载体 < 二级载体内标注”，每增加一层嵌套，载体与标注各占一个连续层级。
- 默认载体为阻断式：显示后，其下所有标注层必须隐藏且不可命中，最高阻断层关闭后逐级恢复。仅明确允许与下层同时操作的非模态浮层可以声明 `data-ds-overlay-mode="nonmodal"`；允许值只有 `modal`、`nonmodal`，省略等同 `modal`。
- 运行时根据 DOM 嵌套关系、可见性及出现顺序分配深度。`data-ds-overlay-root` 必须是定位元素并覆盖自身交互区域；嵌套载体应放在父载体 DOM 内，禁止用业务自定义 z-index 绕过运行时分层。
- `ds-*` CSS 类、`data-ds-*` 属性和 `--ds-*` 变量属于框架保留命名空间，业务页面不得覆盖或复用；业务 DOM 只允许使用契约明确开放的 `data-ds-prototype-root`、`data-ds-spec-anchor`、`data-ds-scroll-consumer`、`data-ds-overlay-root` 和 `data-ds-overlay-mode`。

## 5. 变更影响

`changeImpact` 允许：

| 值 | 含义 | 规范同步要求 |
|---|---|---|
| `business` | 业务规则、字段、口径或功能变化 | 必须存在本次新增/修改规范项 |
| `interaction` | 触发、反馈、跳转、状态或生命周期变化 | 必须存在本次新增/修改规范项 |
| `visual-only` | 仅颜色、间距、排版、尺寸等视觉调整 | 可不修改规范正文 |
| `none` | 本版本未涉及 | 不应保留本版本红色规范项 |

页面、模块、区块和末级条目继续使用 `changeType: new | modified | existing`。显示编号由运行时按模块和区块顺序派生。

## 6. 构建与版本

运行：

```bash
python3 "$CORE_ROOT/scripts/build_prototype_v3.py" 原型-v3/app --output 原型-v3
```

构建器统一完成：

- 根据项目注册表生成 Index 导航与项目概述。
- 将独立规范数据内嵌到页面 manifest。
- 将固定标注 CSS、页面通信运行时和框架按钮内嵌到每个页面。
- 写入 `protocolVersion`、`frameworkVersion`、`specSchemaVersion`、`generatedBy`、`buildId` 和框架指纹。
- 向生成的 Index 和页面注入 `Cache-Control: no-cache, no-store, must-revalidate`、`Pragma: no-cache` 与 `Expires: 0` meta，作为无服务器配置权时的辅助缓存声明。

版本职责：

- `protocolVersion`：Index 与页面消息协议；当前为 5。
- `frameworkVersion`：Index、标注、规范渲染框架；当前为 3.14.0。
- `specSchemaVersion`：技术规范数据结构；当前为 5。
- `frameworkFingerprint`：固定框架资产校验值；同一交付目录必须一致。
- `buildId`：项目构建内容标识；使用 SHA-256 内容哈希的前 12 位小写十六进制字符。哈希输入必须包含框架版本、生成器、Index/公共 JS/CSS、项目概述 DOM 模板与 CSS、标准化项目配置以及注册表引用的全部页面与规范源文件。相同输入必须得到相同 ID，任一有效输入变化必须得到新 ID；禁止使用需读取上次构建状态的递增计数器。

Index 缓存换版规则：

- 用户始终只需访问稳定的 `index.html`，无需在入口 URL 手工添加版本号。
- 左侧导航链接保持 `#page=<file>`，项目注册表中的 `page.file` 不写版本参数。
- Index 加载子页面时必须通过 `new URL(page.file, window.location.href)` 构造地址，再以 `searchParams.set("v", BUILD_ID)` 附加版本，以兼容既有查询参数和 `file://`。
- `buildId` 必须同时写入 Index 运行时、Index `ds-build-id` meta 和每个页面 manifest，同一交付目录不得混用。
- HTML meta 无法代替服务端 HTTP 响应头，也无法追溯修复已被长期缓存的旧 Index；当最新 Index 被浏览器取得后，iframe 的 `v=<buildId>` 才是后续子页面换版的主保障。

## 7. 校验与验收

先校验源数据，再校验构建产物：

```bash
python3 "$CORE_ROOT/scripts/validate_prototype_v3.py" 原型-v3/app
python3 "$CORE_ROOT/scripts/validate_prototype_v3.py" 原型-v3/app --output 原型-v3
```

校验至少覆盖：

- 页面 ID、输出文件、导航分组、终端声明唯一且有效。
- 新标准项目的业务版本/PRD绑定、需求映射、演示说明完整；页面/模块/PRD编号引用有效，PRD缺失或截断等未检查情况不得显示为完整通过。
- 控件说明页使用独立导航分组、关闭技术规范，并与业务页面分开统计。
- 图解说明页使用独立导航分组、关闭技术规范，在项目概述单独统计且不混入实际业务端。
- 图解页的主阅读方向、图例、节点、连线、条件、责任与例外表达完整；主图在默认缩放下可读且无错连、裁切或遮挡。
- 规范中的 `pageId` 引用目标存在、不是当前页面且属于控件说明页。
- 英文输出文件名、一个项目概述页、分端页面数据完整。
- 概述页的名词解析、原型修改记录、FAQ 和埋点声明结构完整；`changeLogOrder` 必须为 `newest-first`，修改记录按版本倒序且最旧批次为 V1.0，同批次共用日期时间且版本/日期时间/终端连续可合并，操作类型与时间格式合法，FAQ 角色/状态合法。
- 禁止 `target` 和独立 markers；规范模块与稳定锚点一一对应。
- 业务或交互修改存在本版本规范项。
- 每个控件级模块仅有一份非空 `controls` 清单，且按控件类型完整声明数据源、默认值、必填/必选、选项、约束与可选范围；保存/提交按钮必须具有校验及通过/不通过结果，操作按钮必须具有明确点击结果。
- 所有页面框架版本、指纹与 `buildId` 一致，Index 运行时与 `ds-build-id` meta 使用同一 `buildId`。
- Index 导航链接不含版本参数，iframe 请求统一附加 `v=<buildId>`，Index 与全部生成页都具有辅助缓存 meta。
- 最终页面包含内嵌框架且无 `app/` 运行依赖；绑定 PRD 与源数据变化后，生成页的业务绑定和 `buildId` 必须与当前输入一致。

浏览器验收先按演示路径检查主流程、关键失败和恢复、数据重置及保留，并验证追溯表对应的实际场景；结构校验不能替代功能验收。再覆盖终端切换、页面规范默认展示、标注点击、按住 Space 拖拽、触摸板双指 X/Y/斜向平移、输入控件空格输入、局部滚动区域独占及边界锁定、无实际溢出时交还画布、浏览器历史导航保护、iframe 视觉边界、弹窗标注生命周期、嵌套载体逐层遮蔽与关闭恢复、真实内容高度和控制台错误。

页面高度规则：Index 切换页面时必须先将 iframe 高度重置为最小测量高度（当前为 `16px`，需大于 iframe 边框总高度），阻断上一页高度对新页面 `100vh` 的污染并保证子页面渲染帧继续执行；PC/平板由内容完成布局后上报真实高度，手机先使用声明的设备高度建立模拟视口。Index 不设置页面最大高度，也不得把上一页高度作为新页面的最小高度。

## 8. Index 与页面交互模式

- 默认状态必须允许直接操作原型页面的按钮、链接、表单、滚动和弹窗，不显示持久拖拽开关。
- 点击左侧导航切换页面时，必须取消尚未执行的画布手势并将画布 X/Y 平移量及 Index 原型区域滚动位置重置为 0；保留用户当前缩放比例。新页面不得继承上一页的拖拽或双指平移位置。
- 按下 Space 后立即进入临时拖拽状态，不设置长按延迟；松开 Space 后立即恢复原型操作状态。
- 工具栏保留状态切换：默认状态展示“按住 [Space] 拖拽页面”，临时拖拽状态展示“松开 [Space] 操作原型”。`Space` 使用同一套 CSS 键帽图案并位于动词与操作结果之间；状态切换同时更新文案、键帽状态色及无障碍说明。禁止依赖系统 Emoji 或 Canvas 图片资产。
- 底部工具栏固定分为左侧控制区与右侧提示区；终端和缩放控件位于左侧，动态操作提示位于右侧。工具栏和提示外层按最长状态预留宽度，当前状态内容在内层整体居中，左右内边距与工具栏中终端按钮左侧留白一致；按下/松开不得引发布局位移。
- Index 与 iframe 页面都必须监听 Space。页面获得焦点时，通过 `space-pan-start`、`space-pan-end` 通知 Index，由 Index 统一控制拖拽遮罩和提示状态。
- Space 作为拖拽修饰键时必须阻止浏览器空格滚屏和按钮二次触发；焦点位于 `input`、`textarea`、`select`、`contenteditable`、ARIA textbox/combobox 时，不接管 Space，保留正常输入。
- `event.repeat` 不得重复进入状态。Index 窗口失焦、页面隐藏、iframe 卸载、页面切换或按下 Escape 时，必须恢复默认操作状态，避免拖拽状态卡死。
- iframe 按住 Space 后点击 Index 拖拽遮罩会自然触发子页面 `blur`；该 `blur` 是手势的一部分，不得发送 `space-pan-end`。最终结束由松开 Space、页面隐藏/卸载或 Index 的失焦保护负责。
- 拖拽开始后键盘焦点可能转移到 Index，导致 Space `keyup` 只由 Index 收到。Index 每次结束拖拽都必须发送 `space-pan-reset`，清除子页面的按键占用状态，保证下一次 Space 手势可以重新开始。
- 默认操作状态直接点击 iframe 内的真实标注并发送 `spec-module-selected`；临时拖拽状态由遮罩接管全部指针事件，不同时支持标注点击。
- Index 不得建立透明标注点击代理，页面不得发送 `spec-markers-layout`；缩放和拖拽只作用于整个 iframe，不再计算或同步标注映射坐标。
- Index 原型区域必须支持触摸板双指 X/Y/斜向平移；Index 空白区域直接处理 `wheel`，iframe 页面通过 `canvas-pan` 转发未被局部滚动区域独占的手势。使用 `requestAnimationFrame` 合并连续位移，`Ctrl/Cmd + wheel` 不接管。
- 局部滚动容器使用 `data-ds-scroll-consumer="x"`、`"y"` 或 `"both"` 显式声明可消费方向。运行时必须同时检查声明方向、实际 overflow 及 scroll/client 尺寸；只有声明且真实溢出的容器才取得独占权。
- 鼠标位于有效局部滚动容器内时，由 DOM 上最内层有效容器独占整次触摸板手势：只滚动其声明且真实溢出的方向，未声明方向直接丢弃；到达顶部、底部或左右边界后继续拦截，不得把任一轴传递给外层滚动容器或 Index 画布。声明容器没有实际溢出时不取得独占权，手势继续由外层有效容器或 Index 处理。
- `data-ds-scroll-consumer` 统一应用 `overscroll-behavior: none`，作为浏览器原生滚动链的补充保护；Space 临时拖拽始终由 Index 遮罩优先接管，不受滚动区域独占限制。
- PC/平板基础页面由内容自然撑高，不建立整页内部滚动容器；表格、当前显示的弹窗/抽屉及固定设备模拟视口才声明局部滚动。业务布局可自由使用 Grid/Flex，但不得用固定视口高度截断整页内容。
- Index 与页面统一设置 `overscroll-behavior-x: none`。所有有效横向 wheel 位移由非被动监听器取消默认行为，避免触发浏览器前进/后退；小于 1px 的横向噪声按 0 处理。
- iframe 禁止使用实体边框；实体边框会形成父页与子页均接收不到 wheel 的命中死区。使用不参与命中测试的外描边阴影表达页面边界。

协议 v5 页面 → Index 消息：

| 消息 | 含义 |
|---|---|
| `space-pan-start` | iframe 内按下 Space，请求进入临时拖拽状态 |
| `space-pan-end` | iframe 内松开 Space，或页面隐藏/卸载时，请求恢复页面操作状态 |
| `canvas-pan` | iframe 内未被局部滚动容器消费的 X/Y 位移，请求 Index 平移原型画布 |

协议 v5 Index → 页面消息：

| 消息 | 含义 |
|---|---|
| `space-pan-reset` | Index 已结束临时拖拽，清除页面内部 Space 占用状态 |

## 9. 新迭代重置

引用既有原型开启新迭代时，只重置源数据，不修改构建产物：

```bash
python3 "$CORE_ROOT/scripts/reset_prototype_v3.py" 原型-v3/app --apply
```

重置后：

- 所有旧 `new`、`modified` 改为 `existing`。
- 页面 `versionChanges` 清空。
- 页面和模块 `changeImpact` 改为 `none`。
- 当前迭代的 `overview.prototypeChangeLog` 清空；FAQ 不自动清空，由新项目初始化或作者指令决定。
- 再录入本次变更，重新构建并校验。
