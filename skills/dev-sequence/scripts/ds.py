#!/usr/bin/env python3
"""Offline Dev Sequence project, review and evidence tools. Standard library only."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
import review_records as records
import review_choice as choices
from datetime import datetime
from pathlib import Path

VERSION = "1.4.1"
PROTOCOL = 1
CORE = Path(__file__).resolve().parent.parent
STAGES = {
    "prd": ("需求", "requirements", []),
    "ui": ("UI设计", "ui", ["brief"]),
    "proto": ("原型", "prototype", ["prd", "ui"]),
    "tech": ("技术方案", "tech", ["prd", "prototype"]),
    "code": ("代码", "code", ["prd", "prototype", "tech", "tasks"]),
    "test": ("测试验收", "test", ["prd", "prototype", "tech", "code"]),
}
SKIP = {".git", "__pycache__", ".DS_Store", "node_modules", "验收记录", ".dev-sequence"}


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, text, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".ds-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if exclusive:
            # Atomic no-clobber commit: readers never see a half-written frozen file.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_write(path, value, exclusive=False):
    write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n", exclusive)


def inside(root, value, must_exist=True):
    """Resolve a project path while rejecting symlinks, including ancestor symlinks."""
    raw = Path(value)
    candidate = raw if raw.is_absolute() else root / raw
    candidate = Path(os.path.abspath(candidate))
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        raise ValueError(f"路径越出项目: {value}")
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"不接受符号链接: {value}")
    if must_exist and not candidate.exists():
        raise ValueError(f"文件不存在: {value}")
    return candidate


@contextlib.contextmanager
def locked(root):
    directory = inside(root, ".dev-sequence", False)
    directory.mkdir(exist_ok=True)
    lock = inside(root, ".dev-sequence/write.lock", False)
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError("项目正被其他写入占用，或有待核实的遗留 write.lock")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def inline(text):
    return html.escape(str(text))


def render(md, title, data=None):
    """Render our small Markdown subset safely. Raw input HTML is always escaped."""
    out, code, table, listing = [], False, False, False
    def end_blocks():
        nonlocal table, listing
        if table:
            out.append("</tbody></table></div>")
            table = False
        if listing:
            out.append("</ul>")
            listing = False
    for line in md.splitlines():
        if line.startswith("```"):
            end_blocks()
            out.append("</code></pre>" if code else "<pre><code>")
            code = not code
            continue
        if code:
            out.append(inline(line) + "\n")
            continue
        if line.startswith("|"):
            if re.fullmatch(r"[| :\-]+", line):
                continue
            cells = line.strip().strip("|").split("|")
            if not table:
                end_blocks()
                out.append('<div class="table"><table><thead><tr>' + "".join("<th>" + inline(c.strip()) + "</th>" for c in cells) + "</tr></thead><tbody>")
                table = True
            else:
                out.append("<tr>" + "".join("<td>" + inline(c.strip()) + "</td>" for c in cells) + "</tr>")
            continue
        end_blocks()
        heading = re.match(r"^(#{1,6}) (.*)", line)
        if heading:
            n = len(heading[1])
            out.append(f"<h{n}>{inline(heading[2])}</h{n}>")
        elif line.startswith("- "):
            out.append("<p class='bullet'>• " + inline(line[2:]) + "</p>")
        elif line:
            out.append("<p>" + inline(line) + "</p>")
    end_blocks()
    if code:
        out.append("</code></pre>")
    payload = canonical(data or {}).replace("<", "\\u003c")
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{inline(title)}</title>
<style>:root{{font-family:system-ui,sans-serif;color:#172536;background:#f2f5f9;line-height:1.65}}body{{max-width:1120px;margin:32px auto;padding:0 22px}}main{{padding:30px;background:white;border:1px solid #d9e1ec;border-radius:14px}}h1{{font-size:27px}}h2{{margin-top:38px;border-bottom:2px solid #dde7f4;padding-bottom:10px}}h3{{color:#235cab}}.table{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}}th,td{{border:1px solid #d9e1ec;padding:9px;text-align:left;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}}th{{background:#edf3fb}}pre{{background:#eff3f7;padding:16px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}}p{{white-space:pre-wrap;overflow-wrap:anywhere}}footer{{font-size:12px;color:#52657b;margin-top:28px}}@media print{{body{{margin:0;max-width:none}}main{{border:0;padding:0}}h2,h3{{break-after:avoid}}tr{{break-inside:avoid}}}}</style>
<main>{''.join(out)}<footer>Dev Sequence · 内容源 SHA-256: {digest(md.encode())} · 历史视图，当前有效性请运行 status</footer></main><script id="ds-data" type="application/json">{payload}</script></html>'''


def pair(root, stem, md, data=None, exclusive=False):
    for suffix, content in [(".md", md), (".html", render(md, stem.name, data))]:
        write(inside(root, str(stem) + suffix, False), content, exclusive)


def database(root):
    return records.read_state(root, "验收数据.json", {"protocolVersion": PROTOCOL, "suiteVersion": VERSION, "stages": {}})


def stage_data(db, stage):
    return db["stages"].setdefault(stage, {"rounds": [], "confirmation": {"status": "pending"}})


def cell(value):
    if not isinstance(value, str):
        value = canonical(value)
    return value.replace("|", "｜").replace("\n", " ⏎ ")


def save(root, db):
    db["suiteVersion"] = VERSION
    db["reviewLayoutVersion"] = 3
    json_write(inside(root, records.state_path("验收数据.json"), False), db)
    records.save_views(root, db)


def rules(root, stage):
    node, skill, _ = STAGES[stage]
    source = inside(root, f"{node}/.review-skill.md", False)
    if not source.exists():
        template = CORE.parent / f"dev-sequence-{skill}" / "review-standard.md"
        if not template.is_file():
            raise ValueError(f"未安装阶段资源: dev-sequence-{skill}")
        write(source, template.read_text(encoding="utf-8"), True)
    md = source.read_text(encoding="utf-8")
    if not md.strip():
        raise ValueError("验收规则不能为空")
    write(inside(root, f"{node}/验收规则.html", False), render(md, "验收规则"))
    return source


def protocol_files():
    return {name: (CORE / "references" / name).read_bytes() for name in ("core-contract.md", "review-protocol.md", "external-skills.md", "automatic-handoff.md", "final-test-isolation.md", "review-layout.md")}


def collect(root, stage, spec, max_files=500, max_chars=400000):
    if not isinstance(spec, dict) or not isinstance(spec.get("artifacts"), list) or not spec["artifacts"]:
        raise ValueError("artifacts 必须是非空数组")
    scope = spec.get("scope")
    if not isinstance(scope, dict) or not str(scope.get("description", "")).strip() or not isinstance(scope.get("exclusions"), list):
        raise ValueError("scope 需要 description 和 exclusions 数组")
    exclusions = []
    for exclusion in scope["exclusions"]:
        if not isinstance(exclusion, dict) or not exclusion.get("path") or not str(exclusion.get("reason", "")).strip():
            raise ValueError("排除项必须包含 path 和 reason")
        exclusions.append(inside(root, exclusion["path"], False))
    checks = spec.get("checklist")
    if not isinstance(checks, list) or not checks:
        raise ValueError("checklist 必须非空")
    ids = []
    for item in checks:
        if not isinstance(item, dict) or not item.get("id") or not str(item.get("text", "")).strip() or item.get("kind", "semantic") not in {"semantic", "automated"}:
            raise ValueError("检查项需要唯一 id、text 和有效 kind")
        ids.append(item["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("检查项 ID 重复")
    context = spec.get("context", [])
    if not isinstance(context, list):
        raise ValueError("context 必须为数组")
    context = [dict(c) for c in context]
    if any(c.get("role") == "review-standard" for c in context):
        raise ValueError("review-standard 由工具绑定节点实际规则，无需自行声明")
    standard = f"{STAGES[stage][0]}/.review-skill.md"
    context.append({"role": "review-standard", "path": standard, "version": "content-sha256"})
    roles = {c.get("role") for c in context}
    missing = set(STAGES[stage][2]) - roles
    if missing:
        raise ValueError("缺少必要上下文角色: " + ",".join(sorted(missing)))
    files, manifest, chars = {}, [], 0
    for role, entries in [("artifact", spec["artifacts"]), ("context", context)]:
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("输入声明必须是对象")
            if entry.get("notApplicable") is True:
                if role == "artifact" or entry.get("role") == "review-standard" or not str(entry.get("reason", "")).strip() or "path" in entry or "version" in entry:
                    raise ValueError("不适用声明缺理由或混用了文件字段")
                manifest.append({"role": entry.get("role"), "notApplicable": True, "reason": entry["reason"]})
                continue
            if not entry.get("path") or not str(entry.get("version", "")).strip():
                raise ValueError("实际输入必须有 path 和 version")
            path = inside(root, entry["path"])
            candidates = [path] if path.is_file() else sorted(path.rglob("*"))
            count = 0
            for candidate in candidates:
                relative = candidate.relative_to(root)
                explicit_review_context = (role == "context" and entry.get("role") in {"prior-review", "review-evidence"} and candidate == path and "验收记录" in relative.parts and not any(p in SKIP - {"验收记录"} for p in relative.parts))
                if any(p in SKIP for p in relative.parts) and not explicit_review_context:
                    continue
                candidate = inside(root, relative)
                if candidate.is_dir():
                    continue
                if any(candidate == x or x in candidate.parents for x in exclusions):
                    continue
                count += 1
                key = relative.as_posix()
                payload = candidate.read_bytes()
                try:
                    text = payload.decode("utf-8")
                    if "\x00" in text:
                        raise UnicodeError()
                    kind = "text"
                except UnicodeError:
                    text, kind = None, "binary"
                if key not in files:
                    files[key] = payload
                    chars += len(text) if text is not None else 0
                if len(files) > max_files or chars > max_chars:
                    raise ValueError("输入超限；请拆分范围或显式调整限制，不截断")
                if entry.get("role") == "prd" and text:
                    from prototype_content import prd_version, versions_equal
                    declared = prd_version(text)
                    if declared and not versions_equal(declared, entry["version"]):
                        raise ValueError(f"PRD 版本声明与原文不符: {key}")
                manifest.append({"path": key, "version": entry["version"], "role": entry.get("role", role), "sha256": digest(payload), "kind": kind})
            if count == 0:
                raise ValueError(f"输入被全部排除或没有实际文件: {entry['path']}")
    protocols = protocol_files()
    bundle = {"suiteVersion": VERSION, "protocolVersion": PROTOCOL, "stage": stage, "spec": spec, "manifest": manifest, "protocols": {n: digest(b) for n, b in protocols.items()}}
    return digest(canonical(bundle).encode()), manifest, files, protocols


def refresh(root, db):
    for stage, data in db["stages"].items():
        for rnd in data["rounds"]:
            reason = None
            integrity_invalid = False
            if rnd.get("result") and "resultValidAtRecord" not in rnd:
                frozen_path = rnd.get("frozenReport")
                try:
                    original = load(inside(root, frozen_path))["round"] if frozen_path else None
                    rnd["resultValidAtRecord"] = bool(original and original.get("status") != "stale")
                except (ValueError, OSError, KeyError, TypeError):
                    rnd["resultValidAtRecord"] = False
            try:
                fp, _, _, _ = collect(root, stage, rnd["spec"], **rnd["limits"])
                if fp != rnd["fingerprint"]:
                    reason = "产物、前置上下文、规则或共享协议已变化"
                snapshot = inside(root, rnd["snapshot"])
                frozen = load(snapshot / "request.json")
                if frozen != rnd["spec"]:
                    reason = "冻结请求被修改"
                    integrity_invalid = True
                for name, sha in rnd["snapshotHashes"].items():
                    if digest(inside(root, str(snapshot / name)).read_bytes()) != sha:
                        reason = "评审快照被修改"
                        integrity_invalid = True
                for name, sha in rnd.get("reportHashes", {}).items():
                    if digest(inside(root, name).read_bytes()) != sha:
                        reason = "冻结报告被修改"
                        integrity_invalid = True
                for name, sha in rnd.get("auxHashes", {}).items():
                    if digest(inside(root, name).read_bytes()) != sha:
                        reason = "冻结请求或提示词被修改"
                        integrity_invalid = True
                for evidence in rnd.get("result", {}).get("independentTest", {}).get("evidenceFiles", []):
                    if digest(inside(root, evidence["path"]).read_bytes()) != evidence["sha256"]:
                        reason = "独立测试设计或执行证据已变化"
                        integrity_invalid = True
            except (ValueError, OSError, KeyError, TypeError) as exc:
                reason = str(exc)
                integrity_invalid = True
            rnd["evidenceInvalid"] = integrity_invalid
            if reason:
                rnd["status"] = "stale"
                rnd["staleReason"] = reason
            elif rnd.get("result") and rnd["status"] == "passed":
                unresolved = records.unresolved_blockers(data, rnd)
                if unresolved:
                    rnd["status"] = "changes-requested"
                    rnd["validationReasons"] = ["历史阻断问题尚未独立验证关闭：" + ", ".join(unresolved)]
        if data["rounds"]:
            latest = data["rounds"][-1]
            confirmation = data["confirmation"]
            if confirmation.get("status") == "accepted" and (confirmation.get("fingerprint") != latest["fingerprint"] or confirmation.get("round") != latest["number"] or latest["status"] not in {"passed", "waived"}):
                confirmation["status"] = "stale"


def prepare(root, args):
    if args.kind == "fix":
        raise ValueError("修复不再新建轮次；请用reply向问题提出轮次追加答复、修复说明和证据，再prepare新review轮次独立复验")
    db = database(root)
    choice = choices.for_prepare(db, args)
    rules(root, args.stage)
    spec = load(args.spec)
    spec["priorIssues"] = records.review_context(stage_data(db, args.stage))
    if args.stage == "test":
        if not args.producer_session or not args.producer_session.strip():
            raise ValueError("最终测试必须绑定原生产会话，以便强制新会话设计、执行和复验")
        forbidden = {args.producer_session}
        for data_ in db["stages"].values():
            for old in data_["rounds"]:
                if old.get("producerSession"):
                    forbidden.add(old["producerSession"])
                if old.get("stage") == "test":
                    identity = old.get("result", {}).get("independentTest", {}).get("sessionId")
                    if identity:
                        forbidden.add(identity)
                    reviewer_id = old.get("result", {}).get("reviewer", {}).get("sessionId")
                    if reviewer_id:
                        forbidden.add(reviewer_id)
        ledger_value = records.read_state(root, "交接数据.json", {"jobs": {}})
        if ledger_value:
            for job in ledger_value.get("jobs", {}).values():
                if job.get("stage") == "test" and job.get("reviewerId"):
                    forbidden.add(job["reviewerId"])
        spec["independentTestPolicy"] = {"required": True, "purpose": "independent-design-and-execution", "forbiddenSessionIds": sorted(forbidden)}
    fp, manifest, files, protocols = collect(root, args.stage, spec, args.max_files, args.max_chars)
    refresh(root, db)
    data = stage_data(db, args.stage)
    number = max((r["number"] for r in data["rounds"]), default=0) + 1
    suffix = f"{args.stage}-r{number:03d}"
    workdir = records.process_dir(args.stage, number)
    snaprel = workdir / "评审资料"
    snap = inside(root, snaprel, False)
    if snap.exists():
        raise ValueError("评审资料目录已存在；请核对遗留轮次，不覆盖")
    snap.mkdir(parents=True)
    for path, payload in files.items():
        dest = snap / "files" / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
    for name, payload in protocols.items():
        dest = snap / "protocol" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
    json_write(snap / "request.json", spec, True)
    json_write(snap / "manifest.json", {"inputFingerprint": fp, "inputs": manifest}, True)
    template = {"stage": args.stage, "round": number, "inputFingerprint": fp, "overall": "not_checked", "reviewer": {"name": "", "freshContext": False, "isolationEvidence": "", "sessionId": ""}, "items": [{"id": c["id"], "result": "not_checked", "evidence": "", "comment": ""} for c in spec["checklist"]], "issues": [], "verifications": [], "summary": "", "notChecked": []}
    if args.stage == "test":
        template["independentTest"] = {"sessionId": "", "freshContext": False, "designedHere": False, "executedHere": False, "designEvidence": "", "executionEvidence": "", "testCaseIds": [], "buildVersion": "", "environment": "", "evidenceFiles": []}
    json_write(snap / "result-template.json", template, True)
    rnd = {"stage": args.stage, "number": number, "createdAt": now(), "kind": args.kind, "method": args.method, "producerSession": args.producer_session or None, "fingerprint": fp, "status": "pending", "spec": spec, "snapshot": snaprel.as_posix(), "limits": {"max_files": args.max_files, "max_chars": args.max_chars}}
    rnd["snapshotHashes"] = {p.relative_to(snap).as_posix(): digest(p.read_bytes()) for p in sorted(snap.rglob("*")) if p.is_file()}
    request_md = f"# 验收请求 · {suffix}\n\n轮次：r{number:03d}\n\n输入指纹：{fp}\n\n## 请求\n\n```json\n{json.dumps(spec, ensure_ascii=False, indent=2)}\n```\n\n## 实际输入清单\n\n```json\n{json.dumps(manifest, ensure_ascii=False, indent=2)}\n```\n"
    write(inside(root, workdir / "验收请求.md", False), request_md, True)
    prompt = None
    if args.method == "agent":
        assignment = "你是独立评审者。在新建且不继承生产历史的上下文执行；不能把生产对话 fork 后当作独立验收。\n只评审本轮声明范围，不修改交付源文件，不添加产品需求。"
        if args.stage == "test":
            assignment = f"你是最终测试执行者，必须在全新且不继承生产历史的会话中独立设计并实际执行测试。不是仅审阅生产者的测试报告。先从需求/AC、约束和待测版本形成或修订自己的计划与TC，再实际运行、核对预期和实际结果。可参考旧用例，但不能只照搬勾选。不得修改受测代码或验收规则；允许在测试验收/编写测试计划、用例、脚本和业务测试报告，在{workdir.as_posix()}/保存执行证据。"
        prompt_md = f"""# 独立验收提示词 · {suffix}

{assignment}
实际阅读和验证，不能凭摘要、文件名、任务勾选或生产者结论通过。

项目资料入口：{snaprel.as_posix()}。若本地路径不可访问，请索取本轮完整评审资料包；不能假定已读。
先读 request.json、manifest.json、protocol/ 下规则和 files/ 下本阶段实际验收规则，再读清单中的必要原文和产物。二进制/图片须实际查看；无法查看标未检查。
验收阶段：{args.stage}；轮次：r{number:03d}；类型：{args.kind}。
输入指纹：{fp}，必须原样回传。

## 本轮范围和排除

```json
{json.dumps(spec['scope'], ensure_ascii=False, indent=2)}
```

## 逐项验收清单

```json
{json.dumps(spec['checklist'], ensure_ascii=False, indent=2)}
```

## 复现与资料定位

依据请求中的 instructions（若有）、阶段规则及实际源码执行合适的只读检查。若执行会写业务数据、发送消息、发布或产生费用，应检查已有授权，否则标明未执行。
目录 files/ 保留项目相对路径；运行依赖不在快照时标明，不能暗中换用不同版本。复验先检查当前产物，再结合请求中提供的历史问题/回归范围，不仅核对修复者回复。

## 问题与结果

问题使用跨轮次稳定 ID，记录 severity（critical/major/minor/suggestion）、status（open/fixed/answered/verified/waived）、description、source、evidence；必要时 resolution。
issues只列本轮新发现、新增问题点或重新打开的问题。重复旧问题沿用ID；有新的问题点用changeType=updated，复发用reopened。独立新问题使用新ID，可用relatedIssueId关联历史项。
旧问题的复验填verifications，每项为issueId、result（pass/fail/not_checked）、evidence、comment；不要复制问题全文。request.json的priorIssues是自动冻结的未关闭问题及实际答复，须先检查当前产物再核对；不能仅凭修复者答复关闭，也不能靠省略历史阻断问题报通过。已验证关闭且本次无异常的旧问题无需重复报告，但受影响回归仍须实际执行并记入items/证据。
每个 checklist ID 必须唯一对应一个结果 pass/fail/not_checked，记录具体证据。没执行不能写 pass。无问题时 issues=[]，不捏造问题。
填入真实 reviewer.name、freshContext=true 和 isolationEvidence；已知平台会话 ID 时填 sessionId，不能编造。生产会话已知 ID：{args.producer_session or '未提供'}。
缺资料、超出能力或无法执行的项目写 not_checked 和原因。主对话答复与修复追加在问题提出轮次，不单独创建fix轮次；下一次独立验收或复验才新建轮次。
使用 result-template.json 的字段输出完整 JSON（填写副本，不修改冻结快照），并附人可读结论。报告目标：{records.round_stem(args.stage, number)}.md 与 .html，由生产侧统一导入生成；冻结JSON与执行材料放本轮.过程目录。
不能改输入指纹或删检查项。通过要求当前基线、全部必需项有真实证据且无未复验阻塞问题；豁免需真实 approvedBy、reason、evidence，不自行批准。
"""
        if args.stage == "test":
            prompt_md += "\n## 最终测试强制关卡\n\nindependentTest 必须如实填写：sessionId与本次reviewer.sessionId相同、freshContext/designedHere/executedHere为true，提供计划与TC设计证据、实际执行证据、非空testCaseIds、待测buildVersion与environment。evidenceFiles至少包含一份kind=design和一份kind=execution的非空项目内文件，每项填写path、kind、实际sha256；保存本轮新产生的计划/用例和执行日志。只审阅旧报告或缺执行条件不能报pass，应填not_checked及原因后仍回传。修复后的复验也必须再开新会话，不能复用本轮或历史测试会话；禁止ID以request.json的independentTestPolicy为准。\n"
        prompt = str(workdir / "验收提示词.md")
        write(inside(root, prompt, False), prompt_md, True)
    auxiliary = [str(workdir / "验收请求.md")]
    if prompt:
        auxiliary.append(prompt)
    rnd["auxHashes"] = {path: digest(inside(root, path).read_bytes()) for path in auxiliary}

    if choice is not None:
        rnd["reviewChoice"] = choices.bind_round(choice, number)
    data["rounds"].append(rnd)
    if data["confirmation"].get("status") == "accepted":
        data["confirmation"]["status"] = "stale"
    save(root, db)
    return {"stage": args.stage, "round": number, "inputFingerprint": fp, "snapshot": str(snaprel), "prompt": prompt,
            "reviewChoice": rnd.get("reviewChoice"),
            "nextAction": "dispatch-native" if choice and choice["method"] == "native" else "deliver-third-party" if choice else "local-check-or-fix",
            "note": "按已登记选择执行；第三方须在当前对话输出完整提示词并交付资料；工具不创建聊天。"}


def evaluate(rnd, result):
    if not isinstance(result, dict):
        raise ValueError("验收结果必须为结构化对象")
    if result.get("stage") != rnd["stage"] or result.get("round") != rnd["number"]:
        raise ValueError("结果阶段或轮次与本轮不符")
    if result.get("inputFingerprint") != rnd["fingerprint"]:
        raise ValueError("结果指纹与本轮不符")
    if result.get("overall") not in {"pass", "fail", "needs_improvement", "not_checked", "waived"}:
        raise ValueError("无效 overall")
    reviewer = result.get("reviewer")
    if not isinstance(reviewer, dict) or not isinstance(reviewer.get("name"), str) or not reviewer["name"].strip():
        raise ValueError("缺少真实评审者")
    if rnd["method"] == "agent":
        if reviewer.get("freshContext") is not True or not str(reviewer.get("isolationEvidence", "")).strip():
            raise ValueError("缺少新上下文隔离声明或依据")
        if rnd.get("producerSession") and rnd["producerSession"] == reviewer.get("sessionId"):
            raise ValueError("生产与评审会话相同，不能独立验收")
    if rnd["stage"] == "test" and rnd["kind"] == "review":
        if "independentTest" in result and not isinstance(result["independentTest"], dict):
            raise ValueError("independentTest必须是结构化对象，失败结果也不能保存损坏结构")
        policy = rnd["spec"].get("independentTestPolicy", {})
        forbidden = set(policy.get("forbiddenSessionIds", []))
        if rnd.get("producerSession"):
            forbidden.add(rnd["producerSession"])
        if reviewer.get("sessionId") in forbidden:
            raise ValueError("最终测试或复验必须新会话，不能复用生产或历史测试会话")
        if result["overall"] == "pass":
            test = result.get("independentTest", {})
            required_text = ("sessionId", "designEvidence", "executionEvidence", "buildVersion", "environment")
            if not isinstance(test, dict) or any(not isinstance(test.get(k), str) or not test[k].strip() for k in required_text):
                raise ValueError("最终测试通过必须提供新会话独立设计和实际执行的证据")
            if test["sessionId"] != reviewer.get("sessionId") or test["sessionId"] in forbidden or any(test.get(k) is not True for k in ("freshContext", "designedHere", "executedHere")):
                raise ValueError("最终测试必须由本轮新会话独立设计并执行，不能仅审报告")
            ids = test.get("testCaseIds")
            if not isinstance(ids, list) or not ids or any(not isinstance(k, str) or not k.strip() for k in ids) or len(ids) != len(set(ids)):
                raise ValueError("最终测试须提供真实且唯一的TC编号")
            if reviewer.get("freshContext") is not True or rnd["method"] == "script":
                raise ValueError("仅脚本检查不能替代新会话独立测试验收")
    checks = rnd["spec"]["checklist"]
    items = result.get("items")
    if not isinstance(items, list) or any(not isinstance(i, dict) or not isinstance(i.get("id"), str) for i in items) or len(items) != len(checks) or {i.get("id") for i in items} != {c["id"] for c in checks}:
        raise ValueError("结果必须逐项唯一对应全部检查清单")
    for item in items:
        if item.get("result") not in {"pass", "fail", "not_checked"} or not str(item.get("evidence", "")).strip():
            raise ValueError("检查项须有有效结论和证据/未检查原因")
    issues = result.get("issues")
    if not isinstance(issues, list):
        raise ValueError("issues 必须为数组")
    issue_ids = set()
    for issue in issues:
        if not isinstance(issue, dict) or any(not isinstance(issue.get(k), str) or not issue[k].strip() for k in ("id", "description", "source", "evidence")):
            raise ValueError("问题缺少编号、描述、来源或证据")
        if issue.get("kind", "problem") not in {"problem", "suggestion", "question"}:
            raise ValueError("问题kind必须为problem/suggestion/question")
        if issue["id"] in issue_ids or issue.get("severity") not in {"critical", "major", "minor", "suggestion"} or issue.get("status") not in {"open", "fixed", "answered", "verified", "waived"}:
            raise ValueError("问题编号重复或严重度/状态无效")
        issue_ids.add(issue["id"])
        if issue.get("changeType", "new") not in {"new", "updated", "reopened"}:
            raise ValueError("changeType须为new/updated/reopened")
        if not isinstance(issue.get("resolution", ""), str):
            raise ValueError("问题处理说明resolution须为文本")
    if not isinstance(result.get("summary"), str) or not result["summary"].strip():
        raise ValueError("缺少结论说明")
    if not isinstance(result.get("notChecked", []), list):
        raise ValueError("notChecked 必须为数组")
    if result["overall"] == "waived":
        waiver = result.get("waiver", {})
        if any(not str(waiver.get(k, "")).strip() for k in ("reason", "approvedBy", "evidence")):
            raise ValueError("正式豁免缺少批准人、理由或真实依据")
        return "awaiting-verification" if rnd["kind"] == "fix" else "waived"
    if rnd["kind"] == "fix":
        return "awaiting-verification"
    verifications = result.get("verifications", [])
    if not isinstance(verifications, list) or any(not isinstance(v, dict) or v.get("result") not in {"pass", "fail", "not_checked"} for v in verifications):
        raise ValueError("verifications须包含有效复验结论")
    blocking = any(i["severity"] in {"critical", "major"} and i["status"] != "verified" for i in issues)
    verification_failed = any(v["result"] == "fail" for v in verifications)
    verification_unchecked = any(v["result"] == "not_checked" for v in verifications)
    automated = all(c.get("kind", "semantic") == "automated" for c in checks)
    if result["overall"] == "pass" and all(i["result"] == "pass" for i in items) and not blocking and not verification_failed and not verification_unchecked and not result.get("notChecked"):
        if rnd["method"] == "script" and not automated:
            return "pending"
        return "passed"
    if blocking or verification_failed or any(i["result"] == "fail" for i in items) or result["overall"] in {"fail", "needs_improvement"}:
        return "changes-requested"
    return "pending"


def validate_test_evidence(root, rnd, result):
    if rnd["stage"] != "test" or rnd["kind"] != "review":
        return
    ledger_value = records.read_state(root, "交接数据.json", {"jobs": {}})
    if ledger_value:
        session = result.get("reviewer", {}).get("sessionId")
        if any(job.get("stage") == "test" and job.get("reviewerId") == session and job.get("state") == "failed" for job in ledger_value.get("jobs", {}).values()):
            raise ValueError("最终测试不能复用已失败交接的测试会话，必须全新会话")
    if result.get("overall") != "pass":
        return
    files = result.get("independentTest", {}).get("evidenceFiles")
    if not isinstance(files, list) or not files or any(not isinstance(e, dict) for e in files):
        raise ValueError("最终测试须提供本轮设计和执行的真实证据文件")
    if not {"design", "execution"} <= {e.get("kind") for e in files}:
        raise ValueError("最终测试须同时具有design和execution证据")
    for evidence in files:
        path = inside(root, evidence.get("path", ""))
        if not path.is_file() or path.stat().st_size == 0 or digest(path.read_bytes()) != evidence.get("sha256"):
            raise ValueError("独立测试证据缺失、为空或SHA-256不符")


def record(root, args):
    db = database(root)
    data = stage_data(db, args.stage)
    rnd = next((r for r in data["rounds"] if r["number"] == args.round), None)
    if not rnd:
        raise ValueError("不存在该轮次")
    if "result" in rnd:
        raise ValueError("已有冻结报告，不允许覆盖；请创建新轮次")
    result = load(args.result)
    state = evaluate(rnd, result)
    records.validate_verifications(data, rnd, result)
    validate_test_evidence(root, rnd, result)
    if state == "passed":
        unresolved = records.unresolved_blockers(data, rnd, result)
        if unresolved:
            state = "changes-requested"
            rnd["validationReasons"] = ["历史阻断问题尚未独立验证关闭：" + ", ".join(unresolved)]
    refresh(root, db)
    rnd["result"] = result
    rnd["recordedAt"] = now()
    rnd["status"] = "stale" if rnd.get("staleReason") else state
    rnd["resultValidAtRecord"] = rnd["status"] != "stale"
    frozen_rel = records.round_report_path(args.stage, args.round)
    rnd["frozenReport"] = str(frozen_rel)
    frozen_path = inside(root, frozen_rel, False)
    if frozen_path.exists():
        frozen = load(frozen_path)
        original = frozen.get("round", {})
        stable = ("stage", "number", "fingerprint", "spec", "snapshot", "snapshotHashes", "auxHashes", "kind", "method", "producerSession", "limits", "createdAt", "frozenReport")
        if frozen.get("stage") != args.stage or original.get("result") != result or any(original.get(k) != rnd.get(k) for k in stable) or not original.get("recordedAt"):
            raise ValueError("存在不同内容或不完整的冻结报告，不能覆盖或恢复")
        rnd["recordedAt"] = original["recordedAt"]
        rnd["resultValidAtRecord"] = original.get("resultValidAtRecord", original.get("status") != "stale")
    else:
        # Raw result is immutable; Markdown/HTML are derived views with append-only replies.
        json_write(frozen_path, {"stage": args.stage, "round": dict(rnd)}, True)
    rnd["reportHashes"] = {str(frozen_rel): digest(frozen_path.read_bytes())}

    save(root, db)
    return {"status": rnd["status"], "report": str(records.round_stem(args.stage, args.round)) + ".html", "source": str(frozen_rel)}


def initialize(root, args):
    stages = args.stages.split(",")
    if not stages or any(s not in STAGES for s in stages):
        raise ValueError("未知阶段 ID")
    for stage in stages:
        rules(root, stage)
    defaults = {
        "项目理解.md": "# 项目理解\n\n仅登记已确认事实，任务开始前阅读。\n\n## 目标与边界\n\n待根据真实输入登记。\n\n## 架构、目录与约束\n\n待检查项目后登记。\n\n## 当前阶段、风险与更新时间\n\n尚未登记，不补造历史。\n",
        "交互记录.md": "# 交互记录\n\n按真实交互连续追加用户完整原文、接收/提交时间和最终结果摘要；不补造历史。\n",
        "工程原则.md": "# 项目工程原则\n\n## 已确认原则\n\n尚未确认。执行者应依据真实项目与用户决定填写，不将空模板视为已通过的原则。\n\n## 复杂度与例外\n\n记录原则来源、例外理由、较简单替代方案及实际批准依据。\n",
    }
    for path, content in defaults.items():
        target = inside(root, path, False)
        if not target.exists():
            write(target, content, True)
    project_file = inside(root, ".dev-sequence/project.json", False)
    if not project_file.exists():
        json_write(project_file, {"suiteVersion": VERSION, "name": args.name or root.name, "createdAt": now(), "confirmationPolicy": "manual", "stages": stages}, True)
    else:
        project = load(project_file)
        project["stages"] = list(dict.fromkeys(project.get("stages", []) + stages))
        json_write(project_file, project)
    db = database(root)
    for stage in stages:
        stage_data(db, stage)
    refresh(root, db)
    save(root, db)
    return {"project": str(root), "stages": stages, "overwrittenExistingRules": False}


def confirm(root, args):
    db = database(root)
    refresh(root, db)
    data = stage_data(db, args.stage)
    if not data["rounds"]:
        raise ValueError("尚无验收轮次")
    rnd = data["rounds"][-1]
    if not args.by.strip() or not args.evidence.strip():
        raise ValueError("确认须有真实确认人和依据")
    if args.decision == "accepted":
        if rnd["status"] != "passed" and not (rnd["status"] == "waived" and args.accept_waiver):
            save(root, db)
            raise ValueError("当前版本未通过；正式豁免需显式接受")
        if rnd["method"] == "script":
            raise ValueError("纯脚本检查不能独立推进阶段")
    event = {"status": args.decision, "by": args.by, "evidence": args.evidence, "time": now(), "fingerprint": rnd["fingerprint"], "round": rnd["number"], "mode": args.mode}
    existing = data["confirmation"]
    if all(existing.get(k) == event[k] for k in ("status", "by", "evidence", "fingerprint", "round", "mode")):
        return dict(existing, duplicate=True)
    data.setdefault("confirmationHistory", []).append(event.copy())
    data["confirmation"] = event
    save(root, db)
    return event


def inventory(root, args):
    records = []
    for raw in args.inputs:
        path = inside(root, raw)
        for p in ([path] if path.is_file() else sorted(path.rglob("*"))):
            rel = p.relative_to(root)
            if any(part in SKIP for part in rel.parts):
                continue
            p = inside(root, rel)
            if p.is_file():
                records.append({"source": rel.as_posix(), "sha256": digest(p.read_bytes()), "observed": False, "adoption": "待实际查看后填写"})
    for url in args.urls:
        if not re.match(r"^https?://", url):
            raise ValueError("参考 URL 只接受 http/https")
        records.append({"source": url, "observed": False, "adoption": "仅登记链接，尚未访问；执行者须实际打开"})
    if not records:
        raise ValueError("没有参考资料")
    name = f"参考清单-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    md = "# UI 参考清单\n\n工具只登记来源，不证明已经查看。\n\n| 来源 | 指纹 | 已实际查看 | 采纳说明 |\n|---|---|---|---|\n"
    for item in records:
        md += f"| {cell(item['source'])} | {item.get('sha256', '')} | 否 | {cell(item['adoption'])} |\n"
    pair(root, Path("UI设计") / name, md, records, True)
    return {"references": len(records), "manifest": "UI设计/" + name + ".md"}


def analyze(root, args):
    source = inside(root, args.source)
    value = load(source)
    rows = value.get("traceability", []) if isinstance(value, dict) else value
    if not isinstance(rows, list) or not rows:
        raise ValueError("traceability 必须为非空数组")
    errors = []
    for i, row in enumerate(rows):
        if not row.get("requirementId") or not row.get("acceptanceIds"):
            errors.append(f"第{i+1}行缺 requirementId 或 acceptanceIds")
        for link in row.get("links", []):
            try:
                inside(root, link["path"])
            except (ValueError, KeyError) as exc:
                errors.append(f"第{i+1}行: {exc}")
        for needed in args.require:
            if not row.get(needed):
                errors.append(f"第{i+1}行缺少 {needed}")
    return {"checkedRows": len(rows), "errors": errors, "status": "changes-requested" if errors else "structural-pass", "limit": "仅检查结构、必要引用和文件存在；语义、真实实现和测试结果须独立评审。"}


def tasks(root, args):
    source = inside(root, args.source)
    value = load(source)
    rows = value.get("tasks") if isinstance(value, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("tasks 必须为非空数组")
    ids, graph = set(), {}
    for row in rows:
        if any(not row.get(k) for k in ("id", "description", "sourceRefs", "outputs", "doneWhen", "validation")):
            raise ValueError("任务缺少 ID/说明/来源/产物/完成条件/验证方法")
        if row["id"] in ids:
            raise ValueError("任务 ID 重复")
        ids.add(row["id"])
        if row.get("state") not in {"todo", "in-progress", "blocked", "implemented", "verified"}:
            raise ValueError("任务状态无效")
        if row["state"] in {"implemented", "verified"} and not row.get("evidence"):
            raise ValueError("已实施/已验证任务须有真实证据")
        if not isinstance(row.get("dependsOn", []), list):
            raise ValueError("dependsOn 必须为数组")
        graph[row["id"]] = row.get("dependsOn", [])
    visiting, visited = set(), set()
    def visit(key):
        if key not in ids:
            raise ValueError("未知任务依赖: " + key)
        if key in visiting:
            raise ValueError("任务依赖存在环")
        if key in visited:
            return
        visiting.add(key)
        for dep in graph[key]:
            visit(dep)
        visiting.remove(key)
        visited.add(key)
    for key in ids:
        visit(key)
    md = "# 实施任务\n\n结构检查不证明实现已完成；状态声明须有实际证据。\n\n| ID | 说明 | 来源 | 依赖 | 产物 | 完成条件 | 验证 | 状态 | 证据 |\n|---|---|---|---|---|---|---|---|---|\n"
    for row in rows:
        md += "| " + " | ".join(cell(row.get(k, "")) for k in ("id", "description", "sourceRefs", "dependsOn", "outputs", "doneWhen", "validation", "state", "evidence")) + " |\n"
    stem = source.with_suffix("").relative_to(root)
    pair(root, stem, md, value)
    return {"status": "structural-pass", "tasks": len(rows), "verifiedClaims": sum(r["state"] == "verified" for r in rows), "view": str(stem) + ".html"}


def main(argv=None):
    import handoff
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init"); p.add_argument("--stages", default=",".join(STAGES)); p.add_argument("--name")
    p = sub.add_parser("rules"); p.add_argument("--stage", choices=STAGES, required=True)
    p = sub.add_parser("prepare"); p.add_argument("--stage", choices=STAGES, required=True); p.add_argument("--spec", type=Path, required=True); p.add_argument("--method", choices=["agent", "human", "script"], required=True); p.add_argument("--kind", choices=["review", "fix"], default="review"); p.add_argument("--producer-session"); p.add_argument("--max-files", type=int, default=500); p.add_argument("--max-chars", type=int, default=400000)
    p = sub.add_parser("record"); p.add_argument("--stage", choices=STAGES, required=True); p.add_argument("--round", type=int, required=True); p.add_argument("--result", type=Path, required=True)
    sub.add_parser("status")
    p = sub.add_parser("reply"); p.add_argument("--stage", choices=STAGES, required=True); p.add_argument("--round", type=int, required=True); p.add_argument("--issue", required=True); p.add_argument("--by", required=True); p.add_argument("--message", required=True); p.add_argument("--disposition", choices=["fixed", "answered", "declined"], required=True); p.add_argument("--evidence", default="")
    p = sub.add_parser("review-views", help="刷新验收阅读视图；显式升级模板时备份旧页面"); p.add_argument("--upgrade-template", action="store_true")
    p = sub.add_parser("confirm"); p.add_argument("--stage", choices=STAGES, required=True); p.add_argument("--by", required=True); p.add_argument("--evidence", required=True); p.add_argument("--decision", choices=["accepted", "changes-requested"], default="accepted"); p.add_argument("--mode", choices=["manual", "preauthorized"], default="manual"); p.add_argument("--accept-waiver", action="store_true")
    p = sub.add_parser("reference-inventory"); p.add_argument("--inputs", nargs="*", default=[]); p.add_argument("--urls", nargs="*", default=[])
    p = sub.add_parser("analyze"); p.add_argument("--source", required=True); p.add_argument("--require", nargs="*", default=[])
    p = sub.add_parser("tasks"); p.add_argument("--source", required=True)
    p = sub.add_parser("render"); p.add_argument("--source", required=True); p.add_argument("--output", required=True)
    handoff.add_commands(sub)
    choices.add_command(sub)
    args = parser.parse_args(argv)
    try:
        root = args.project.absolute()
        if not root.is_dir() or root.is_symlink() or root.resolve() != root:
            raise ValueError("项目根须为已存在的真实目录，不使用符号链接路径")
        inside(root, "验收记录", False)
        with locked(root):
            if args.command in handoff.HANDLERS: output = handoff.HANDLERS[args.command](root, args)
            elif args.command == "init": output = initialize(root, args)
            elif args.command == "rules":
                output = {"rules": str(rules(root, args.stage))}
                db = database(root); refresh(root, db); save(root, db)
            elif args.command == "prepare": output = prepare(root, args)
            elif args.command == "review-choice": output = choices.choose(root, args)
            elif args.command == "record": output = record(root, args)
            elif args.command == "reply": output = records.reply(root, args)
            elif args.command == "review-views": output = records.rebuild(root, args)
            elif args.command == "confirm": output = confirm(root, args)
            elif args.command == "reference-inventory": output = inventory(root, args)
            elif args.command == "analyze": output = analyze(root, args)
            elif args.command == "tasks": output = tasks(root, args)
            elif args.command == "render":
                source, dest = inside(root, args.source), inside(root, args.output, False)
                if source == dest or dest.suffix.lower() != ".html":
                    raise ValueError("输出须为不同的 HTML 文件")
                write(dest, render(source.read_text(encoding="utf-8"), source.stem)); output = {"output": str(dest)}
            else:
                db = database(root); refresh(root, db); save(root, db)
                output = {s: {"status": d["rounds"][-1]["status"] if d["rounds"] else "pending", "confirmation": d["confirmation"], "reviewChoice": choices.latest(d)} for s, d in db["stages"].items()}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 2 if output.get("status") in {"pending", "changes-requested", "awaiting-verification", "stale", "waived"} else 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
