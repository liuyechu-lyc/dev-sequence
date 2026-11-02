# Changelog

## 1.4.0 · 2026-11-03

- 发现、答复及修复归属同一验收轮次；reply追加实际处理，fixed须提供证据，不再创建独立fix轮次。
- 历史问题使用verifications简要复验并关联回原记录；只有新发现、新问题点或复发才显示完整条目。省略历史阻断项不能通过，修复者答复不能代替独立验证。
- 总览与单轮MD/HTML同源，按阶段和轮次组织；HTML支持轮次、问题、答复及证据折叠和全部展开/收起，保留待处理提示和原始结论。
- 保留旧轮次编号和冻结证据；默认旧页面升级前备份，自定义旧页面需明确使用review-views --upgrade-template。
- Keep findings, responses, and repairs in the originating round. Re-verify historical issues through compact evidence-backed references, present round-based collapsible records, and preserve immutable evidence and existing round IDs.
- 完成118项离线回归（含折叠操作与链接检查）、7个入口校验和全阶段临时安装验证；新上下文独立复现并复验了过期结果、问题复发、同秒答复和异常输入。验证使用合成数据，不替代真实业务试用。发布目录整理移除历史验证日志、过期报告、旧版指南与绘图提示词；保留维护测试和必要示例，使用全新仓库历史发布。

## 1.3.0 · 本机更新基线

- 接入本机现有的明确验收方式选择、分阶段阅读目录、同源答复链、固定HTML壳与内嵌数据、结果时间排序和历史阻断关卡。
- 本次1.4.0基于已安装版本升级，保留新会话独立测试、自动回传、修复与全新会话复验闭环。

## 1.2.0 · 2026-11-02

- 按六项特点重做深色使用指南，增加阶段输入/产物对照和最终测试强制规则；准备首次公开GitHub发布、MIT许可、贡献说明与CI。
- Rebuilt the visual guide with six features, stage inputs/deliverables, and the final-test rule; prepared the public GitHub project with MIT licensing, contribution guidance, and CI.
- 打包与校验排除仓库元数据、缓存和输出目录，避免Git检出和重复构建污染安装包。
- 重新提炼六项特点，补全六阶段输入、业务产物、共同验收产物与目录说明，同步中英文README及文字指南。
- Refined the feature summary and documented all six stages' inputs, deliverables, shared acceptance artifacts, and locations in the bilingual README and Chinese guide.
- 强制最终测试在新会话独立设计并实际执行，不允许仅评审生产者报告。
- 自动回传原会话修复，复验另开全新会话；禁止复用生产或历史测试上下文。
- 增加最终测试结果与证据文件关卡，同步总控、测试入口、工作流、验收标准、模板与交接提示词。
- Final acceptance now requires independent test design/execution in a fresh context; fixes return to production and re-verification starts another fresh context. Passing results require identity and verifiable design/execution artifacts.


## 1.1.0 · 2026-11-02

### 中文

- 本模型在不继承生产历史的新上下文中独立验收，结果自动回传原对话。
- 原对话校验阶段、轮次、身份和指纹后，导入完整结果并修复、补证、复验或推进。
- 明确授权且信息、权限与执行条件充分时，在授权范围内全自动执行；未授权时保留阶段确认。
- 增加授权历史、交接记录、防重复处理、暂停恢复和中断后的同内容提交恢复。
- 保留验收规则在节点根目录；记录、报告、请求和提示词统一在项目根验收记录目录。
- 更新深色卡片风格使用指南，覆盖特点、简单安装、使用和六阶段产物清单；中英文README同步。

### English

- Fresh same-model review contexts return completion to the original conversation.
- The originating agent validates and imports full results before fixing, re-verifying, confirming, or advancing.
- Explicit scoped authorization enables automatic execution when inputs, permissions, and host capabilities are sufficient.
- Added authorization history, durable handoffs, deduplication, pause/resume, and interrupted-commit recovery.
- Preserved stage-local acceptance rules and project-level review records.
- Updated the dark-card usage guide and bilingual README documentation.

## 1.0.0

Initial self-contained coordinator, six stage skills, prototype framework, review tools, installation packages, and bilingual documentation.
