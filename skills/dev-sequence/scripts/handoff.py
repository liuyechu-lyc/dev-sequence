"""Durable same-model review handoffs. Host agents perform dispatch and delivery."""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import ds
import review_records as records
import review_choice as choices

POLICY = ".dev-sequence/automation.json"
LEDGER = records.state_path("交接数据.json")


def policy(root):
    path = ds.inside(root, POLICY, False)
    return ds.load(path) if path.exists() else {"mode": "manual", "stages": [], "allowed": {}}


def ledger(root):
    return records.read_state(root, "交接数据.json", {"version": 1, "jobs": {}, "repairState": {}})


def save(root, value):
    ds.json_write(ds.inside(root, LEDGER, False), value)
    # Dispatch details appear in the matching round; no separate root-level MD/HTML clutter.
    ds.save(root, ds.database(root))


def configure(root, args):
    value = ds.load(args.spec)
    if value.get("mode") not in {"manual", "review-only", "automatic"}:
        raise ValueError("mode 必须是 manual/review-only/automatic")
    auth = value.get("authorization", {})
    if any(not isinstance(auth.get(k), str) or not auth[k].strip() for k in ("by", "source", "text")):
        raise ValueError("必须记录直接来自使用者的授权人、原文与可定位来源")
    stages = value.get("stages")
    if not isinstance(stages, list) or not stages or any(s not in ds.STAGES for s in stages) or len(stages) != len(set(stages)):
        raise ValueError("必须列出有效且不重复的授权阶段")
    if stages != [s for s in ds.STAGES if s in stages]:
        raise ValueError("阶段按研发依赖顺序排列，可选择子集")
    allowed = value.get("allowed", {})
    keys = {"review", "notifyOrigin", "repair", "advance", "autoConfirm"}
    if not isinstance(allowed, dict) or any(k not in keys or not isinstance(v, bool) for k, v in allowed.items()):
        raise ValueError("allowed 包含无效授权字段")
    if value["mode"] in {"review-only", "automatic"} and not all(allowed.get(k) is True for k in ("review", "notifyOrigin")):
        raise ValueError("自动交接需要独立验收及回传原对话授权")
    if value["mode"] == "automatic" and not all(allowed.get(k) is True for k in keys):
        raise ValueError("全自动须明确授权验收、回传、修复、推进和自动确认")
    if not str(value.get("scope", "")).strip():
        raise ValueError("须明确授权业务范围")
    limits = value.setdefault("limits", {})
    for key, default in [("maxRepairRounds", 3), ("maxNoProgress", 2)]:
        limits.setdefault(key, default)
        if type(limits[key]) is not int or not 1 <= limits[key] <= 20:
            raise ValueError("修复和无进展上限须为1到20的整数")
    value["updatedAt"] = ds.now()
    ds.json_write(ds.inside(root, POLICY, False), value)
    # Preserve authorization revisions as append-only events, rather than silently replacing history.
    path = ds.inside(root, records.state_path("自动化授权历史.json"), False)
    history = records.read_state(root, "自动化授权历史.json", [])
    history.append(copy.deepcopy(value))
    ds.json_write(path, history)

    return {"mode": value["mode"], "stages": stages, "scope": value["scope"], "note": "每阶段仍须实际检查输入与权限；工具不证明授权原文真实性。"}


def stop(root, args):
    value = policy(root)
    value["mode"] = "manual"
    value["allowed"] = {}
    value["stoppedAt"] = ds.now()
    value["stopEvidence"] = args.evidence
    if not args.evidence.strip():
        raise ValueError("停止须有真实请求依据")
    ds.json_write(ds.inside(root, POLICY, False), value)
    return {"mode": "manual", "note": "已撤回自动动作；仍可收取已有结果，不再自动修复或推进。"}


def current_round(root, stage, number):
    db = ds.database(root)
    ds.refresh(root, db)
    data = ds.stage_data(db, stage)
    rnd = next((r for r in data["rounds"] if r["number"] == number), None)
    if rnd is None:
        raise ValueError("验收轮次不存在")
    return db, data, rnd


def open_job(root, args):
    grant = policy(root)
    if grant.get("mode") not in {"review-only", "automatic"} or args.stage not in grant.get("stages", []) or not all(grant.get("allowed", {}).get(k) for k in ("review", "notifyOrigin")):
        raise ValueError("缺少该阶段本模型独立验收及自动回传授权")
    if args.transport == "thread" and args.origin == "native-parent":
        raise ValueError("独立用户对话路线须提供真实原对话ID，不能猜测")
    db, data, rnd = current_round(root, args.stage, args.round)
    choices.require_native(db, args.stage, rnd)
    if rnd["method"] != "agent" or rnd["status"] == "stale" or "result" in rnd or data["rounds"][-1]["number"] != args.round:
        raise ValueError("须使用当前有效且尚未导入结果的Agent验收轮次")
    value = ledger(root)
    for job in value["jobs"].values():
        if job["stage"] == args.stage and job["round"] == args.round and job["state"] not in {"failed", "consumed"}:
            return {"job": job["id"], "prompt": job["prompt"], "duplicate": True}
    key = "DS-" + uuid.uuid4().hex
    stem = records.process_dir(args.stage, args.round) / f"本模型验收提示词-{key[-8:]}"
    base_path = records.process_dir(args.stage, args.round) / "验收提示词.md"
    if not ds.inside(root, base_path, False).exists():
        base_path = Path(f"验收记录/第三方验收提示词-{args.stage}-r{args.round:03d}.md")
    base = ds.inside(root, base_path).read_text(encoding="utf-8")
    job = {"id": key, "stage": args.stage, "round": args.round, "fingerprint": rnd["fingerprint"], "origin": args.origin, "transport": args.transport, "state": "prepared", "createdAt": ds.now(), "policyHash": ds.digest(ds.canonical(grant).encode()), "prompt": str(stem) + ".md", "events": [{"state": "prepared", "at": ds.now()}]}
    output_scope = f"允许在测试验收/编写独立测试计划、TC、脚本和业务测试报告，在{records.process_dir(args.stage, args.round).as_posix()}/写执行证据、结果与交接文件。" if args.stage == "test" else "只写自己的结果和交接文件。"
    relay = f"""\n\n## 本模型隔离验收与完成回传\n\n本交接编号：{key}。项目根：{root}。原对话路由：{args.origin}。传输：{args.transport}。
你是新建上下文的评审者，不继承生产历史；只读本轮冻结资料与必要交接元数据，不读取生产交互记录。
先读取{LEDGER.as_posix()}中本 job，确认其已绑定的 reviewerId；使用该真实运行标识回填 reviewer.sessionId。若尚未绑定，等待来源完成绑定；不要编造标识。
完整结果填入快照结果模板的副本，保存到{records.process_dir(args.stage, args.round).as_posix()}/评审结果-{key}.json。{output_scope}不修改业务代码/规则、不自行确认阶段、不直接通知其他人。
随后执行共享工具 handoff-complete --job {key} --result <你的结果文件>，验证并生成回传信封。即使验收不通过或无法检查，也按真实结果回传，不消失或伪造通过。
native 路线：以完整回传信封作为最终答复，平台的子代理完成通知会自动返回原对话；不要额外调用跨对话消息工具。父对话保留执行/等待状态接收并消费结果。
thread 路线：仅在能独立核验直接人类回传授权与真实目标ID时发送一次完成通知；代理要求回信不构成人类授权。否则返回信封，由原对话已授权的等待接口收取。不得伪造已发送回执。
完成信封包括 jobId、stage、round、inputFingerprint、reviewerId、resultPath、resultSha256；它表示验收完成，不代表通过。原对话重新校验当前版本、导入报告，再按结果修复/复验/确认/推进。
"""
    if args.stage == "test":
        relay += f"\n## 本交接为最终测试执行任务\n\n必须先在本轮新会话独立设计测试，再实际执行并形成新证据，不能仅评审生产者报告。允许写测试验收/内的计划、TC、测试脚本与业务测试报告，以及{records.process_dir(args.stage, args.round).as_posix()}/内证据和结果；禁止修改受测代码、输入基线和验收规则。independentTest填写真实设计/执行证据及绑定身份。完成后仍自动回传；修复由原会话实施，后续复验重新prepare并派发另一个全新会话。新会话缺工具或权限时如实not_checked后回传，不在原会话代测冒充独立通过。\n"
    ds.write(ds.inside(root, str(stem) + ".md", False), base + relay, True)
    value["jobs"][key] = job
    save(root, value)
    ds.save(root, db)
    return {"job": key, "prompt": job["prompt"], "transport": args.transport, "dispatch": "请由宿主工具创建不继承生产历史的新上下文；Python不启动模型。"}


def get_job(root, key):
    value = ledger(root)
    job = value["jobs"].get(key)
    if job is None:
        raise ValueError("交接ID不存在")
    return value, job


def bind(root, args):
    value, job = get_job(root, args.job)
    if not args.reviewer.strip() or not args.receipt.strip() or args.reviewer == job["origin"]:
        raise ValueError("须绑定不同于原对话的真实评审上下文和创建回执")
    db, _, rnd = current_round(root, job["stage"], job["round"])
    choices.require_native(db, job["stage"], rnd)
    if job["stage"] == "test":
        _, _, rnd = current_round(root, job["stage"], job["round"])
        if args.reviewer in rnd["spec"].get("independentTestPolicy", {}).get("forbiddenSessionIds", []):
            raise ValueError("最终测试必须派发全新会话，不能复用生产或历史测试上下文")
        if any(other["id"] != job["id"] and other["stage"] == "test" and other.get("reviewerId") == args.reviewer for other in value["jobs"].values()):
            raise ValueError("最终测试重试也必须全新会话，不能复用其他交接的测试身份")
    if job.get("reviewerId"):
        if job["reviewerId"] == args.reviewer:
            return {"job": args.job, "state": job["state"], "duplicate": True}
        raise ValueError("交接已绑定其他评审者")
    if job["state"] != "prepared":
        raise ValueError("当前交接不可绑定")
    job.update({"reviewerId": args.reviewer, "dispatchReceipt": args.receipt, "state": "dispatched"})
    job["events"].append({"state": "dispatched", "at": ds.now()})
    save(root, value)
    return {"job": args.job, "state": job["state"], "reviewerId": args.reviewer}


def complete(root, args):
    value, job = get_job(root, args.job)
    if not job.get("reviewerId") or job["state"] not in {"dispatched", "result-ready", "waiting", "consumed"}:
        raise ValueError("交接未派发或已失败")
    result = ds.load(args.result)
    _, data, rnd = current_round(root, job["stage"], job["round"])
    ds.evaluate(rnd, result)
    records.validate_verifications(data, rnd, result)
    ds.validate_test_evidence(root, rnd, result)
    if result.get("reviewer", {}).get("sessionId") != job["reviewerId"]:
        raise ValueError("结果评审身份与绑定上下文不符")
    payload = ds.canonical(result).encode()
    checksum = ds.digest(payload)
    if job.get("resultSha256"):
        if job["resultSha256"] != checksum:
            raise ValueError("已冻结其他结果，不可覆盖回传")
        return dict(job["envelope"], duplicate=True)
    target = str(records.process_dir(job["stage"], job["round"]) / f"回传结果-{job['id']}.json")
    frozen = ds.inside(root, target, False)
    if frozen.exists():
        # A prior attempt may have committed the result before a ledger-write failure.
        if ds.digest(ds.canonical(ds.load(frozen)).encode()) != checksum:
            raise ValueError("存在不同内容的冻结回传结果，不可覆盖")
    else:
        ds.json_write(frozen, result, True)
    envelope = {"event": "review-completed", "jobId": job["id"], "stage": job["stage"], "round": job["round"], "inputFingerprint": job["fingerprint"], "reviewerId": job["reviewerId"], "resultPath": target, "resultSha256": checksum}
    job.update({"state": "result-ready", "resultPath": target, "resultSha256": checksum, "envelope": envelope})
    job["events"].append({"state": "result-ready", "at": ds.now()})
    save(root, value)
    return envelope


def route(root, job, status, value, args):
    grant = policy(root)
    allowed = grant.get("allowed", {})
    active = job["stage"] in grant.get("stages", []) and grant.get("mode") in {"review-only", "automatic"}
    if getattr(args, "conflict", False):
        return "needs-decision", "存在规则冲突，须由使用者决定"
    if not active:
        return "await-user", "自动授权已撤回或不包含当前阶段"
    if ds.digest(ds.canonical(grant).encode()) != job["policyHash"]:
        return "needs-decision", "授权范围或规则已改变，重新核对后再执行"
    try:
        db = ds.database(root)
        rnd = next(r for r in ds.stage_data(db, job['stage'])['rounds'] if r['number'] == job['round'])
        choices.require_native(db, job['stage'], rnd)
    except ValueError as exc:
        return "await-user", str(exc)
    if not (getattr(args, "inputs_ready", False) and getattr(args, "permissions_ready", False) and getattr(args, "readiness_evidence", "").strip()):
        return "needs-input-or-permission", "须实际核对当前输入、权限与执行条件"
    if status == "stale":
        return "prepare-new-review", "当前输入已变化，旧回传不能覆盖新版本"
    if status == "awaiting-verification":
        return "reverify", "修复轮次只记录处理，须新轮次复验"
    if status in {"changes-requested", "pending"}:
        db = ds.database(root)
        rnd = ds.stage_data(db, job["stage"])["rounds"][-1]
        result = rnd.get("result", {})
        signature = ds.digest(ds.canonical({"issues": sorted(i["id"] for i in records.issue_records(ds.stage_data(db, job["stage"])) if i.get("status") != "verified"), "checks": sorted(i["id"] for i in result.get("items", []) if i.get("result") != "pass")}).encode())
        state = value["repairState"].setdefault(job["stage"], {"attempts": 0, "sameFindings": 0})
        counted = state.setdefault("countedJobs", [])
        if job["id"] not in counted:
            state["attempts"] += 1
            state["sameFindings"] = state["sameFindings"] + 1 if state.get("signature") == signature else 1
            state["signature"] = signature
            counted.append(job["id"])
        limits = grant["limits"]
        if state["attempts"] > limits["maxRepairRounds"] or state["sameFindings"] >= limits["maxNoProgress"]:
            return "diagnose", "重复无进展或达到修复上限，先诊断而非无限追加任务"
        if not allowed.get("repair"):
            return "await-user", "当前授权未包含自动修复"
        return ("repair" if status == "changes-requested" else "collect-evidence"), "按真实发现处理，再创建新验收轮次"
    if status == "waived":
        return "await-user", "豁免不自动成为通过，需明确范围接受"
    if status != "passed":
        return "await-user", "没有当前通过结论"
    if grant["mode"] != "automatic" or not allowed.get("autoConfirm") or not allowed.get("advance"):
        return "await-confirmation", "验收通过，等待阶段确认"
    stages = grant["stages"]
    db = ds.database(root)
    ds.refresh(root, db)
    for earlier in stages[:stages.index(job["stage"])]:
        data = ds.stage_data(db, earlier)
        if not data["rounds"] or data["rounds"][-1]["status"] != "passed" or data["confirmation"].get("status") != "accepted":
            return "needs-prerequisite", "授权范围内前置阶段尚未验收确认"
    auth = grant["authorization"]
    ds.confirm(root, SimpleNamespace(stage=job["stage"], by=auth["by"], evidence=auth["source"] + "；" + auth["text"], decision="accepted", mode="preauthorized", accept_waiver=False))
    index = stages.index(job["stage"])
    return ("complete", "授权范围内全部阶段完成") if index == len(stages) - 1 else ("advance", "进入 " + stages[index + 1] + "，先校验该阶段输入")


def receive(root, args):
    value, job = get_job(root, args.job)
    if not args.receipt.strip() or args.sender != job.get("reviewerId"):
        raise ValueError("回传来源与绑定评审上下文不符，或缺实际收取回执")
    if job["state"] == "consumed":
        return {"job": job["id"], "action": job["action"], "duplicate": True, "note": "已处理，不重复修复、确认或推进"}
    if job["state"] not in {"result-ready", "waiting"}:
        raise ValueError("尚无已冻结的回传结果")
    path = ds.inside(root, job["resultPath"])
    result = ds.load(path)
    if ds.digest(ds.canonical(result).encode()) != job["resultSha256"]:
        raise ValueError("回传文件指纹变化")
    db, data, rnd = current_round(root, job["stage"], job["round"])
    ds.evaluate(rnd, result)
    if "result" not in rnd:
        outcome = ds.record(root, SimpleNamespace(stage=job["stage"], round=job["round"], result=path))
    elif rnd["result"] == result:
        outcome = {"status": rnd["status"]}
        ds.save(root, db)
    else:
        raise ValueError("该轮次已导入其他结果")
    if data["rounds"][-1]["number"] != job["round"]:
        action, reason = "ignore-superseded", "通知属于旧轮次，不改变当前轮次推进"
    else:
        action, reason = route(root, job, outcome["status"], value, args)
    waiting = action in {"needs-input-or-permission", "needs-decision", "needs-prerequisite", "await-user", "await-confirmation", "diagnose"}
    decision = {"status": outcome["status"], "action": action, "reason": reason, "at": ds.now()}
    job.update({"state": "waiting" if waiting else "consumed", "action": action, "decision": decision, "deliveryReceipt": args.receipt, "readinessEvidence": getattr(args, "readiness_evidence", "")})
    job["events"].append({"state": job["state"], "action": action, "at": ds.now()})
    save(root, value)
    return {"job": job["id"], **decision, "note": "由原对话在原授权内实际执行 action；通知本身不证明业务通过。"}


def resume(root, args):
    value, job = get_job(root, args.job)
    if args.sender != job.get("reviewerId") or not args.receipt.strip():
        raise ValueError("恢复来源或回执与交接不符")
    if job["state"] != "waiting":
        raise ValueError("仅暂停的交接可恢复；已执行动作不得再次推进")
    grant = policy(root)
    if not args.authorization_evidence.strip():
        raise ValueError("恢复须有实际补充条件或用户决定的依据")
    if args.accept_policy_change:
        if grant.get("mode") not in {"review-only", "automatic"} or job["stage"] not in grant.get("stages", []) or not all(grant.get("allowed", {}).get(k) for k in ("review", "notifyOrigin")):
            raise ValueError("恢复后的新授权未覆盖该交接")
        job.setdefault("authorizationResolutions", []).append({"oldPolicyHash": job["policyHash"], "newPolicyHash": ds.digest(ds.canonical(grant).encode()), "evidence": args.authorization_evidence, "at": ds.now()})
        job["policyHash"] = ds.digest(ds.canonical(grant).encode())
        save(root, value)
    return receive(root, args)


def fail(root, args):
    value, job = get_job(root, args.job)
    returned = job.get("resultPath") or str(records.process_dir(job["stage"], job["round"]) / f"回传结果-{job['id']}.json")
    if job.get("resultSha256") or ds.inside(root, returned, False).exists() or job["state"] in {"result-ready", "waiting", "consumed"}:
        raise ValueError("已有结果，不改写为派发失败")
    if not args.reason.strip() or not args.receipt.strip():
        raise ValueError("失败须记录真实原因与宿主回执")
    job.update({"state": "failed", "reason": args.reason, "failureReceipt": args.receipt})
    job["events"].append({"state": "failed", "at": ds.now()})
    save(root, value)
    return {"job": args.job, "action": "handoff-unavailable", "reason": args.reason}


def add_commands(sub):
    p = sub.add_parser("automation"); p.add_argument("--spec", type=Path, required=True)
    p = sub.add_parser("automation-stop"); p.add_argument("--evidence", required=True)
    p = sub.add_parser("handoff-open"); p.add_argument("--stage", choices=ds.STAGES, required=True); p.add_argument("--round", type=int, required=True); p.add_argument("--transport", choices=["native", "thread"], default="native"); p.add_argument("--origin", default="native-parent")
    p = sub.add_parser("handoff-bind"); p.add_argument("--job", required=True); p.add_argument("--reviewer", required=True); p.add_argument("--receipt", required=True)
    p = sub.add_parser("handoff-complete"); p.add_argument("--job", required=True); p.add_argument("--result", type=Path, required=True)
    p = sub.add_parser("handoff-receive"); p.add_argument("--job", required=True); p.add_argument("--sender", required=True); p.add_argument("--receipt", required=True); p.add_argument("--inputs-ready", action="store_true"); p.add_argument("--permissions-ready", action="store_true"); p.add_argument("--readiness-evidence", default=""); p.add_argument("--conflict", action="store_true")
    p = sub.add_parser("handoff-resume"); p.add_argument("--job", required=True); p.add_argument("--sender", required=True); p.add_argument("--receipt", required=True); p.add_argument("--inputs-ready", action="store_true"); p.add_argument("--permissions-ready", action="store_true"); p.add_argument("--readiness-evidence", default=""); p.add_argument("--conflict", action="store_true"); p.add_argument("--accept-policy-change", action="store_true"); p.add_argument("--authorization-evidence", required=True)
    p = sub.add_parser("handoff-fail"); p.add_argument("--job", required=True); p.add_argument("--reason", required=True); p.add_argument("--receipt", required=True)


HANDLERS = {"automation": configure, "automation-stop": stop, "handoff-open": open_job, "handoff-bind": bind, "handoff-complete": complete, "handoff-receive": receive, "handoff-resume": resume, "handoff-fail": fail}
