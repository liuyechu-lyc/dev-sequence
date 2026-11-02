"""Automatic handoff state-machine checks; transport claims here are synthetic."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import ds
import handoff as h
import test_review as fixtures


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReviewTests()
        self.fixture.setUp()
        self.root = self.fixture.root

    def tearDown(self):
        self.fixture.tearDown()

    def configure(self, mode="automatic", stages=None, **changes):
        value = {"mode": mode, "stages": stages or ["prd"], "scope": "合成工具回归范围", "authorization": {"by": "测试桩", "source": "测试用授权，不代表真实用户", "text": "仅测试状态机"}, "allowed": {"review": True, "notifyOrigin": True, "repair": True, "advance": True, "autoConfirm": True}, "limits": {"maxRepairRounds": 3, "maxNoProgress": 2}}
        value.update(changes)
        path = self.root / "automation-source.json"
        ds.json_write(path, value)
        h.configure(self.root, NS(spec=path))

    def start(self, stage="prd"):
        prepared = self.fixture.prepare(stage)
        job = h.open_job(self.root, NS(stage=stage, round=prepared["round"], transport="native", origin="native-parent"))
        h.bind(self.root, NS(job=job["job"], reviewer="test-reviewer", receipt="合成创建回执"))
        return prepared, job["job"]

    def complete(self, prepared, key, result=None):
        path = self.root / "callback-source.json"
        ds.json_write(path, result or self.fixture.result(prepared))
        return h.complete(self.root, NS(job=key, result=path))

    def receive(self, key, **changes):
        args = {"job": key, "sender": "test-reviewer", "receipt": "合成完成通知回执", "inputs_ready": True, "permissions_ready": True, "readiness_evidence": "合成就绪检查，不代表实际业务", "conflict": False}
        args.update(changes)
        return h.receive(self.root, NS(**args))

    def failed_result(self, prepared):
        result = self.fixture.result(prepared)
        result["overall"] = "fail"
        result["items"][0]["result"] = "fail"
        return result

    def test_explicit_scoped_user_authorization_is_required(self):
        prepared = self.fixture.prepare()
        with self.assertRaisesRegex(ValueError, "授权"):
            h.open_job(self.root, NS(stage="prd", round=prepared["round"], transport="native", origin="native-parent"))
        with self.assertRaisesRegex(ValueError, "原文"):
            self.configure(authorization={})
        with self.assertRaisesRegex(ValueError, "自动交接"):
            self.configure(allowed={"review": True})

    def test_complete_does_not_itself_approve_or_advance(self):
        self.configure()
        prepared, key = self.start()
        envelope = self.complete(prepared, key)
        self.assertEqual(envelope["event"], "review-completed")
        self.assertEqual(h.ledger(self.root)["jobs"][key]["state"], "result-ready")
        self.assertEqual(self.fixture.status()["rounds"][-1]["status"], "pending")
        outcome = self.receive(key)
        self.assertEqual(outcome["action"], "complete")
        self.assertEqual(self.fixture.status()["confirmation"]["status"], "accepted")

    def test_review_only_waits_for_confirmation_after_pass(self):
        self.configure("review-only")
        prepared, key = self.start()
        self.complete(prepared, key)
        self.assertEqual(self.receive(key)["action"], "await-confirmation")
        self.assertEqual(self.fixture.status()["confirmation"]["status"], "pending")

    def test_failed_review_routes_to_repair(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key, self.failed_result(prepared))
        outcome = self.receive(key)
        self.assertEqual(outcome["action"], "repair")
        self.assertEqual(outcome["status"], "changes-requested")

    def test_duplicate_completion_and_delivery_are_idempotent(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        self.assertTrue(self.complete(prepared, key)["duplicate"])
        self.receive(key)
        self.assertTrue(self.receive(key)["duplicate"])
        self.assertEqual(len(self.fixture.status()["confirmationHistory"]), 1)

    def test_rebinding_to_another_reviewer_is_rejected(self):
        self.configure()
        _, key = self.start()
        with self.assertRaisesRegex(ValueError, "其他评审"):
            h.bind(self.root, NS(job=key, reviewer="other-context", receipt="不匹配"))

    def test_mismatched_callback_reviewer_and_sender_are_rejected(self):
        self.configure()
        prepared, key = self.start()
        result = self.fixture.result(prepared)
        result["reviewer"]["sessionId"] = "unbound-reviewer"
        with self.assertRaisesRegex(ValueError, "绑定上下文"):
            self.complete(prepared, key, result)
        self.complete(prepared, key)
        with self.assertRaisesRegex(ValueError, "回传来源"):
            self.receive(key, sender="unbound-reviewer")

    def test_changed_result_cannot_overwrite_frozen_callback(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        result = self.fixture.result(prepared)
        result["summary"] = "另一个结果"
        with self.assertRaisesRegex(ValueError, "不可覆盖"):
            self.complete(prepared, key, result)

    def test_result_file_tampering_is_detected(self):
        self.configure()
        prepared, key = self.start()
        envelope = self.complete(prepared, key)
        path = self.root / envelope["resultPath"]
        result = ds.load(path)
        result["summary"] = "修改"
        ds.json_write(path, result)
        with self.assertRaisesRegex(ValueError, "指纹变化"):
            self.receive(key)

    def test_stale_baseline_cannot_advance(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        (self.root / "output.md").write_text("源内容变化")
        outcome = self.receive(key)
        self.assertEqual(outcome["status"], "stale")
        self.assertEqual(outcome["action"], "prepare-new-review")

    def test_old_round_notification_cannot_drive_current_round(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        latest = self.fixture.prepare()
        self.assertGreater(latest["round"], prepared["round"])
        self.assertEqual(self.receive(key)["action"], "ignore-superseded")
        self.assertEqual(self.fixture.status()["rounds"][-1]["status"], "pending")

    def test_missing_readiness_and_conflicts_pause_auto_actions(self):
        for change, action in [({"permissions_ready": False}, "needs-input-or-permission"), ({"conflict": True}, "needs-decision")]:
            self.configure()
            prepared, key = self.start()
            self.complete(prepared, key)
            self.assertEqual(self.receive(key, **change)["action"], action)

    def test_stop_revokes_automatic_progress_but_keeps_result(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        h.stop(self.root, NS(evidence="合成用户停止请求"))
        self.assertEqual(self.receive(key)["action"], "await-user")
        self.assertEqual(self.fixture.status()["rounds"][-1]["status"], "passed")
        self.assertEqual(self.fixture.status()["confirmation"]["status"], "pending")

    def test_changed_authorization_requires_recheck(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        self.configure(scope="不同授权范围")
        self.assertEqual(self.receive(key)["action"], "needs-decision")

    def test_unconfirmed_selected_predecessor_blocks_progress(self):
        self.configure(stages=["prd", "ui"])
        prepared, key = self.start("ui")
        self.complete(prepared, key)
        self.assertEqual(self.receive(key)["action"], "needs-prerequisite")

    def test_advance_requires_pass_and_confirmation_then_finishes_range(self):
        self.configure(stages=["prd", "ui"])
        prepared, key = self.start("prd")
        self.complete(prepared, key)
        self.assertEqual(self.receive(key)["action"], "advance")
        prepared, key = self.start("ui")
        self.complete(prepared, key)
        self.assertEqual(self.receive(key)["action"], "complete")

    def test_same_unresolved_findings_stop_infinite_repair_loop(self):
        self.configure()
        for expected in ["repair", "diagnose"]:
            prepared, key = self.start()
            self.complete(prepared, key, self.failed_result(prepared))
            self.assertEqual(self.receive(key)["action"], expected)

    def test_failed_dispatch_can_be_retried_as_new_job(self):
        self.configure()
        prepared, key = self.start()
        outcome = h.fail(self.root, NS(job=key, reason="合成宿主失败", receipt="合成失败回执"))
        self.assertEqual(outcome["action"], "handoff-unavailable")
        next_job = h.open_job(self.root, NS(stage="prd", round=prepared["round"], transport="native", origin="native-parent"))
        self.assertNotEqual(next_job["job"], key)

    def test_permissions_pause_resumes_without_reimporting_the_report(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        first = self.receive(key, permissions_ready=False)
        self.assertEqual(first["action"], "needs-input-or-permission")
        self.assertEqual(h.ledger(self.root)["jobs"][key]["state"], "waiting")
        self.assertEqual(self.receive(key)["action"], "complete")
        self.assertEqual(len(self.fixture.status()["confirmationHistory"]), 1)
        self.assertEqual(len(list((self.root / "验收记录/需求验收记录/.过程/第001轮").glob("原始验收报告.json"))), 1)

    def test_predecessor_pause_resumes_after_predecessor_is_confirmed(self):
        self.configure(stages=["prd", "ui"])
        ui, ui_job = self.start("ui")
        self.complete(ui, ui_job)
        self.assertEqual(self.receive(ui_job)["action"], "needs-prerequisite")
        prd, prd_job = self.start("prd")
        self.complete(prd, prd_job)
        self.assertEqual(self.receive(prd_job)["action"], "advance")
        self.assertEqual(self.receive(ui_job)["action"], "complete")

    def test_completion_recovers_result_committed_before_ledger_failure(self):
        self.configure()
        prepared, key = self.start()
        with patch.object(h, "save", side_effect=OSError("模拟冻结后账本写入失败")):
            with self.assertRaises(OSError):
                self.complete(prepared, key)
        self.assertEqual(h.ledger(self.root)["jobs"][key]["state"], "dispatched")
        target = self.root / f"验收记录/需求验收记录/.过程/第001轮/回传结果-{key}.json"
        self.assertTrue(target.exists())
        original = target.read_bytes()
        self.complete(prepared, key)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(self.receive(key)["action"], "complete")

    def test_recovery_rejects_a_different_orphaned_result(self):
        self.configure()
        prepared, key = self.start()
        orphan = self.fixture.result(prepared)
        orphan["summary"] = "另一份不同结果"
        ds.json_write(self.root / f"验收记录/需求验收记录/.过程/第001轮/回传结果-{key}.json", orphan)
        with self.assertRaisesRegex(ValueError, "不同内容"):
            self.complete(prepared, key)

    def test_new_authorization_needs_explicit_resolution_before_resume(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        self.configure(scope="用户明确调整后的范围")
        self.assertEqual(self.receive(key)["action"], "needs-decision")
        args = NS(job=key, sender="test-reviewer", receipt="合成恢复回执", inputs_ready=True, permissions_ready=True, readiness_evidence="合成输入权限核对", conflict=False, accept_policy_change=True, authorization_evidence="合成用户决定，仅测试恢复")
        outcome = h.resume(self.root, args)
        self.assertEqual(outcome["action"], "complete")
        self.assertEqual(len(h.ledger(self.root)["jobs"][key]["authorizationResolutions"]), 1)

    def test_exclusive_frozen_write_never_leaves_partial_target_on_failure(self):
        target = self.root / "atomic-frozen.json"
        with patch.object(ds.os, "fsync", side_effect=OSError("模拟提交前中断")):
            with self.assertRaises(OSError):
                ds.json_write(target, {"complete": True}, True)
        self.assertFalse(target.exists())
        ds.json_write(target, {"complete": True}, True)
        self.assertEqual(ds.load(target), {"complete": True})

    def test_receive_recovers_report_frozen_before_database_save(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        with patch.object(ds, "save", side_effect=OSError("模拟报告冻结后数据库保存失败")):
            with self.assertRaises(OSError):
                self.receive(key)
        self.assertNotIn("result", self.fixture.status()["rounds"][-1])
        reports = {p.name: p.read_bytes() for p in (self.root / "验收记录/需求验收记录/.过程/第001轮").glob("原始验收报告.json")}
        self.assertEqual(len(reports), 1)
        self.assertEqual(self.receive(key)["action"], "complete")
        for name, payload in reports.items():
            self.assertEqual((self.root / "验收记录/需求验收记录/.过程/第001轮" / name).read_bytes(), payload)

    def test_waiting_completed_review_cannot_be_marked_dispatch_failed(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        self.receive(key, permissions_ready=False)
        with self.assertRaisesRegex(ValueError, "已有结果"):
            h.fail(self.root, NS(job=key, reason="迟到的失败", receipt="测试回执"))
        self.assertEqual(h.ledger(self.root)["jobs"][key]["state"], "waiting")
        self.assertEqual(self.receive(key)["action"], "complete")

    def test_report_recovery_fills_missing_view_without_overwriting_source(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        original_write = ds.write
        def interrupted(path, text, exclusive=False):
            if Path(path).name == "第001轮.html":
                raise OSError("模拟视图写入中断")
            return original_write(path, text, exclusive)
        with patch.object(ds, "write", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.receive(key)
        source = self.root / "验收记录/需求验收记录/.过程/第001轮/原始验收报告.json"
        frozen = source.read_bytes()
        self.assertEqual(self.receive(key)["action"], "complete")
        self.assertEqual(source.read_bytes(), frozen)

    def test_report_recovery_rejects_tampered_frozen_source(self):
        self.configure()
        prepared, key = self.start()
        self.complete(prepared, key)
        with patch.object(ds, "save", side_effect=OSError("模拟导入中断")):
            with self.assertRaises(OSError):
                self.receive(key)
        frozen = self.root / "验收记录/需求验收记录/.过程/第001轮/原始验收报告.json"
        value = ds.load(frozen)
        value["round"]["result"]["summary"] = "被篡改的原始结果"
        ds.json_write(frozen, value)
        with self.assertRaisesRegex(ValueError, "冻结报告"):
            self.receive(key)
        self.assertEqual(ds.load(frozen)["round"]["result"]["summary"], "被篡改的原始结果")


if __name__ == "__main__":
    unittest.main()
