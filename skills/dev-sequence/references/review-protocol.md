# Dev Sequence 验收协议 v1（阅读布局 v3）

## 1. 文件与职责

详细的可读目录、总览/明细职责与DOM数据分离见[阅读结构与数据维护](review-layout.md)。

| 位置 | 内容 |
|---|---|
| `节点/.review-skill.md`、`验收规则.html` | 项目实际验收规则及其阅读视图 |
| `验收记录/验收记录总.md`、`.html` | 按阶段、轮次组织问题、答复、处理结果、复验及当前状态 |
| `验收记录/<阶段验收记录>/第NNN轮.md/.html` | 每轮一对阅读记录，含本轮结论、明细与后续处理链 |
| `验收记录/<阶段验收记录>/.过程/第NNN轮/` | 请求、提示词、评审资料、冻结JSON、回传及执行证据 |
| `.dev-sequence/reviews/验收数据.json` | 所有阶段/轮次与追加答复的唯一机器维护源 |
| `.dev-sequence/reviews/交接数据.json`、`自动化授权历史.json` | 内部交接与授权留痕，不额外生成根目录阅读文件 |

MD与HTML内容范围一致。HTML用固定壳和同文件安全JSON数据块渲染，日常只更新数据；失败、未检、失效和豁免必须可见。脚本原子写入并互斥保护。冻结原始JSON和快照不可改写，阅读页允许由同源记录追加答复/后续验证，不覆盖原始发现和结论。

## 2. 创建项目与规则

```sh
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" init --stages prd,ui,proto,tech,code,test
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" rules --stage proto
```

`init` 仅创建缺失文件。仅单阶段时只传该 ID；相关流程 skill 须与总控同级安装。修改规则 MD 后重新运行 `rules` 生成 HTML，刷新验收状态。规则不由通用模板覆盖。

## 3. 请求输入

按本阶段 `templates/review-request.json` 编辑真实请求。`artifacts` 非空；每项 `{path, version}`。`context` 提供本阶段必要角色，实际规则由工具自动加入。路径相对项目根；目录会读取实际文件，不以清单代替。符号链接、越界路径、失效版本、文件缺失、超限或未声明的必要角色拒绝打包。

所有阶段必需实际 review-standard；其他角色为：

- prd：用户来源由实际范围声明。
- ui：brief。
- proto：prd、ui。
- tech：prd、prototype。
- code：prd、prototype、tech、tasks。
- test：prd、prototype、tech、code。

确实不适用的非规则角色使用 `{role, notApplicable:true, reason}`，须由评审核对理由。不能以“未提供”掩盖本应存在的资料。等价输入可以让多个角色指向同一份真实基线，必须标明实际内容足以支撑哪些职责。

复验可用 context.role=prior-review 显式引用验收记录内某一份冻结报告，证据文件可用 review-evidence；工具只纳入明确指定文件，不遍历整个验收记录目录，避免递归收集与自引用。

`scope` 是 `{description, exclusions:[{path,reason}]}`，范围排除必须写理由；排除部分永远不宣称检查。`checklist` 非空，每项 `{id,text,kind}`，kind 为 semantic 或 automated；ID 唯一。纯脚本只适用声明为 automated 的检查，不能独立完成语义验收关卡。

```sh
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" prepare --stage proto --spec request.json --method agent --producer-session ACTUAL_SESSION_IF_KNOWN
```

工具冻结输入、计算指纹、建立轮次，在本轮`.过程/`生成请求与必要的通用提示词；不会为未使用的第三方方式额外生成副本，也不为过程文件生成HTML。默认最多 500 文件及 400000 文本字符，超限先分范围或显式调整限制，不静默截断。图片等二进制可包含快照；评审者必须有查看能力并提供实际观察。主对话修复使用reply追加到问题提出轮次；不再使用prepare --kind fix创建额外轮次。

**选择第三方 Agent 后，执行者必须把生成提示词的完整内容输出到当前对话供复制，同时提供文件链接和资料包。只生成文件不完成提示词交付。**

## 4. 独立性与真实检查

新 AI 评审须新建不继承生产对话的上下文，不使用带生产历史的 fork；本地切换角色只算自审。选择本模型验收时按 [自动交接协议](automatic-handoff.md) 实际创建独立上下文并自动收取完成通知，原对话继续处理。第三方手动评审仍交付完整提示词。Python不直接创建聊天、发送消息或联网，宿主Agent执行已授权交接；能力不足时明确降级。

评审包仅含必要基线与当前产物，不默认附生产对话、推理、内部草稿和生产者通过结论。复验先核对当前产物，再对照历史问题和回归范围。生产者、评审者分离；评审者只输出报告，不修改业务源文件。

结果格式见快照内 `result-template.json`。必须原样回传 stage、round、inputFingerprint，不能将旧轮次结果冒充新验收。清单逐项唯一对应，结论只能 pass/fail/not_checked，每项有具体证据。总结果 pass/fail/needs_improvement/not_checked/waived。问题含稳定 ID、severity、status、description、source、evidence；可用kind=problem/suggestion/question区分问题、建议与疑问，修复建议或处理说明填resolution。没有新发现或变化时issues=[]，不伪造。历史问题复验使用verifications=[{issueId,result,evidence,comment}]，result为pass/fail/not_checked；无需重复问题全文。新问题点可用changeType=updated，复发用reopened；独立新问题另建ID并可用relatedIssueId关联。priorIssues由prepare自动冻结未关闭问题与实际答复。

Agent 结果必须包含 reviewer.name、freshContext=true、isolationEvidence。已知会话 ID 时回填 sessionId；与生产会话相同会拒绝。隔离依据是评审者的真实声明，工具只能校验字段和已知 ID，不能自动证明平台隔离。声明缺失不能通过。人工作为 reviewer 时同样提供真实身份和证据。

## 5. 导入、修复、复验与确认

```sh
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" record --stage proto --round 1 --result result.json
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" status
python3 "$CORE_ROOT/scripts/ds.py" --project "$PROJECT_ROOT" confirm --stage proto --by "实际确认人" --evidence "实际用户授权或确认的可定位依据"
```

导入时重新核对当前源文件、规则、共享协议与请求内容，过期结果标stale，不接受为当前通过，也不能用其中的verified或pass复验关闭历史阻断问题。冻结原始JSON不可覆盖；MD/HTML阅读视图从冻结结果及追加答复生成，不改原结论。问题稳定编号跨轮次引用，不把已修复/已答复视为复验关闭。

阶段状态：pending、changes-requested、awaiting-verification、passed、stale、waived。无阻塞问题、完整清单通过、证据齐全且版本仍有效才 passed。旧版fix记录无论自报何结论都只awaiting-verification；新版不再创建fix轮次。critical/major 问题须 verified 才不阻塞；正式豁免走独立结果并记录 reason/approvedBy/evidence，不能显示 passed。

阶段确认单独存储：待确认/已接受/要求调整、确认人、依据、时间和指纹。`confirm` 默认只接受人工或独立 Agent 的当前 passed；waived 另需显式 `--accept-waiver`。纯脚本局部检查不能让整个阶段自动推进。自动推进必须填真实预授权依据。

`status` 会刷新当前有效性。输入变化或源文件/快照/请求/报告被修改后，受影响轮次与确认失效；历史原始结论保持不改。历史 HTML 是快照，不能代替实时刷新。修复闭环为原轮次reply追加答复/修复证据 → 新review轮次独立复验 → 验证事件关联回原记录，不重写旧结论，不增加独立fix轮次。

本模型回传使用 handoff-complete/handoff-receive。收到通知不等于通过；原对话核对阶段/轮次/指纹/身份，导入完整结果后实际修复、补证、复验或按有效自动授权确认和推进。交接机器数据放`.dev-sequence/reviews/`，回传和必要提示词放对应轮次`.过程/`，本轮阅读页展示交接明细，不额外输出平铺的交接MD/HTML。

### 最终test节点强制要求

按 [最终测试隔离规则](final-test-isolation.md)，在新会话从需求独立设计并实际执行测试，不能仅评审生产者报告。prepare必须提供实际producer-session，自动冻结不可由请求删掉的independentTestPolicy及禁止复用的生产/历史测试标识；handoff-bind拒绝复用。pass结果须有independentTest、真实TC、构建/环境、设计与执行证据文件及SHA-256；工具检查声明和文件，不证明平台内部隔离或测试语义。失败/未检查照常回传；原会话修复后新review轮次再派发全新会话。输出测试产物不应纳入自身输入目录。

## 6. 文件编辑与恢复

编辑验收记录MD不能直接当成状态变更。处理答复用`reply --stage ... --round ... --issue ... --by ... --disposition fixed|answered|declined --message ...`追加，必须写处理结果或不处理的解释；该操作不改变原始结论或自动关闭阻断。真正修正的说明与证据仍追加在提出轮次，仅下一次验收或独立复验创建新review轮次，由record生成同源MD/HTML。对于人工维护的历史 MD，保留原件，先转换并校验结构与证据再导入新轮次；工具不会反向猜测任意 Markdown。

不要删除锁后并发写入。进程异常退出遗留 `.dev-sequence/write.lock` 时先确认无活动写进程，再由使用者或已授权维护操作移除；报告存在但汇总缺失等异常应先核对冻结 JSON，不伪造历史通过。
