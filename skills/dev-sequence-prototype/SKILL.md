---
name: dev-sequence-prototype
description: 将需求与已确认UI规范转为可交互多页面HTML原型，维护页面/模块规范、场景、需求追溯及独立原型验收。
---

# Dev Sequence · 原型设计

将本目录记为 `STAGE_ROOT`，同级 `../dev-sequence` 为 `CORE_ROOT`。这属于本套件的共享运行时；不要求先调用总控，不读取其他研发 skill。独立安装时安装器会同时携带共享运行时。

1. 读取 `CORE_ROOT/references/core-contract.md` 及项目现有上下文，限定本轮目标。
2. 读取 [输入契约](input-contract.md)，接受等价外部资料，缺关键规则时澄清，不机械补跑上游。
3. 按 [工作流](workflow.md) 实施，使用本目录 `templates/`。
原型完整规则读取 `CORE_ROOT/references/prototype-source-contract-v3.md`；控件/图解说明按契约读取专项规则。生成器和框架全部在本套件内。

4. 按 [本阶段验收标准](review-standard.md) 建立项目 `原型/.review-skill.md` 和 `验收规则.html`。保留项目有效特殊标准。
5. 交付当前成果与自检入口后，先按 `CORE_ROOT/references/review-choice.md` 让用户选择本模型、第三方或暂不验收并登记真实依据；无有效选择不得发起验收，仅明确复用授权可沿用。选择验收后按 `CORE_ROOT/references/review-protocol.md` 生成验收请求与快照；AI独立评审读 [评审入口](reviewer.md)，使用不继承生产对话的新上下文。选择第三方时必须在当前对话输出完整提示词，文件放对应阶段本轮`.过程/`，不再生成未使用的重复提示词或过程HTML。
6. 选择本模型验收时读取 `CORE_ROOT/references/automatic-handoff.md`，明确调用不继承生产历史的新上下文同模型评审子代理；完成后自动回传原对话，原对话导入结果并实际修正/复验或推进。第三方手动验收继续交付完整提示词。
7. 修复与复验分轮记录；确认绑定当前版本。只交付本阶段，除非用户已授权继续；信息、权限和明确自动授权齐备时，按交接协议持续执行，不重复请求已授权的确认。

外部 skill 可按需协作；调用前读取 `CORE_ROOT/references/external-skills.md`。规则冲突或分歧列明双方出处和影响，询问使用者；不自行决定优先级，不暂停无关工作。

输出：app/ 注册表、页面及独立规范；index.html 与独立页面；概述、演示/重置/模拟边界、追溯及验收确认。

验收目录遵循`CORE_ROOT/references/review-layout.md`：根部只保留验收记录总MD/HTML，各阶段验收子目录每轮一对MD/HTML，包含问题、建议、答复和处理/不处理解释；请求/快照/冻结JSON/提示词在本轮`.过程/`，机器账本在`.dev-sequence/reviews/`。发现、答复和修复归属同轮，使用reply写回问题提出轮次；下一次独立验收/复验才增加轮次，不另建fix轮次。旧问题复验简要关联，已关闭项不再重复列为新发现，未关闭项不因省略自动消失。总览按轮次组织，HTML支持折叠问题与答复。原始结论冻结，阅读视图同源追加处理链。业务节点根仅规则与业务产物，源码不搬迁。
