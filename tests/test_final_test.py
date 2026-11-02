"""Final-test isolation and design/execution evidence gates (synthetic fixtures)."""
import copy
import unittest
from types import SimpleNamespace as NS

import ds
import review_choice as choices
import handoff as h
import test_review as fixtures


class FinalTestIsolationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ReviewTests()
        self.f.setUp()
        self.root = self.f.root

    def tearDown(self):
        self.f.tearDown()

    def valid_result(self, prepared, session="test-reviewer"):
        value = self.f.result(prepared)
        value["reviewer"]["sessionId"] = session
        files = []
        for kind in ["design", "execution"]:
            path = f"测试验收/{kind}-r{prepared['round']}.txt"
            target = self.root / path
            ds.write(target, "合成回归证据，不是真实业务验收：" + kind)
            files.append({"path": path, "kind": kind, "sha256": ds.digest(target.read_bytes())})
        value["independentTest"] = {"sessionId": session, "freshContext": True, "designedHere": True, "executedHere": True, "designEvidence": "本测试桩的计划与TC说明", "executionEvidence": "本测试桩执行记录", "testCaseIds": ["TC-001"], "buildVersion": "fixture-v1", "environment": "合成隔离回归环境", "evidenceFiles": files}
        return value

    def configure(self):
        path = self.root / "grant.json"
        ds.json_write(path, {"mode": "review-only", "stages": ["test"], "scope": "仅合成测试", "authorization": {"by": "测试桩", "source": "合成授权", "text": "只验证工具"}, "allowed": {"review": True, "notifyOrigin": True}})
        h.configure(self.root, NS(spec=path))

    def test_prepare_forces_policy_even_if_request_tries_to_disable_it(self):
        spec = self.f.spec("test")
        spec["independentTestPolicy"] = {"required": False, "forbiddenSessionIds": []}
        prepared = self.f.prepare("test", spec=spec)
        request = ds.load(self.root / prepared["snapshot"] / "request.json")
        self.assertTrue(request["independentTestPolicy"]["required"])
        self.assertIn("test-producer", request["independentTestPolicy"]["forbiddenSessionIds"])
        template = ds.load(self.root / prepared["snapshot"] / "result-template.json")
        self.assertFalse(template["independentTest"]["executedHere"])

    def test_final_test_requires_producer_identity(self):
        source = self.root / "request.json"
        ds.json_write(source, self.f.spec("test"))
        choices.choose(self.root, NS(stages="test", method="native", reuse="stage", by="测试桩", source="合成选择", text="合成明确选择"))
        with self.assertRaisesRegex(ValueError, "原生产会话"):
            ds.prepare(self.root, NS(stage="test", kind="review", method="agent", producer_session=None, spec=source, max_files=500, max_chars=400000))

    def test_legacy_report_review_alone_cannot_pass(self):
        prepared = self.f.prepare("test")
        with self.assertRaisesRegex(ValueError, "独立设计和实际执行"):
            self.f.record(prepared, self.f.result(prepared))

    def test_both_design_and_execution_must_happen_in_the_new_session(self):
        prepared = self.f.prepare("test")
        for field in ["freshContext", "designedHere", "executedHere"]:
            value = self.valid_result(prepared)
            value["independentTest"][field] = False
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "不能仅审报告"):
                self.f.record(prepared, value)

    def test_valid_evidence_is_recorded_in_matching_md_and_html(self):
        prepared = self.f.prepare("test")
        self.assertEqual(self.f.record(prepared, self.valid_result(prepared))["status"], "passed")
        for suffix in [".md", ".html"]:
            text = (self.root / ("验收记录/测试验收记录/第001轮" + suffix)).read_text()
            self.assertIn("独立测试设计与执行", text)
            self.assertIn("testCaseIds", text)

    def test_missing_or_mismatched_evidence_files_cannot_pass(self):
        prepared = self.f.prepare("test")
        value = self.valid_result(prepared)
        value["independentTest"]["evidenceFiles"][1]["sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.f.record(prepared, value)
        value = self.valid_result(prepared)
        (self.root / value["independentTest"]["evidenceFiles"][1]["path"]).unlink()
        with self.assertRaisesRegex(ValueError, "文件不存在"):
            self.f.record(prepared, value)

    def test_evidence_needs_both_design_and_execution(self):
        prepared = self.f.prepare("test")
        value = self.valid_result(prepared)
        value["independentTest"]["evidenceFiles"] = value["independentTest"]["evidenceFiles"][:1]
        with self.assertRaisesRegex(ValueError, "同时具有"):
            self.f.record(prepared, value)

    def test_later_evidence_mutation_invalidates_pass(self):
        prepared = self.f.prepare("test")
        value = self.valid_result(prepared)
        self.f.record(prepared, value)
        (self.root / value["independentTest"]["evidenceFiles"][1]["path"]).write_text("证据已修改")
        self.assertEqual(self.f.status("test")["rounds"][-1]["status"], "stale")

    def test_script_only_result_cannot_pass_final_test(self):
        prepared = self.f.prepare("test", method="script")
        with self.assertRaisesRegex(ValueError, "仅脚本检查"):
            self.f.record(prepared, self.valid_result(prepared))

    def test_design_and_execution_identity_must_match_the_current_context(self):
        prepared = self.f.prepare("test")
        value = self.valid_result(prepared)
        value["independentTest"]["sessionId"] = "another-context"
        with self.assertRaisesRegex(ValueError, "本轮新会话"):
            self.f.record(prepared, value)

    def test_unexecuted_result_still_returns_truthfully(self):
        prepared = self.f.prepare("test")
        value = self.f.result(prepared)
        value["overall"] = "not_checked"
        value["items"][0].update(result="not_checked", evidence="合成环境缺少执行权限")
        self.assertEqual(self.f.record(prepared, value)["status"], "pending")

    def test_reverification_cannot_reuse_a_previous_test_session(self):
        first = self.f.prepare("test")
        self.f.record(first, self.valid_result(first))
        second = self.f.prepare("test")
        with self.assertRaisesRegex(ValueError, "历史测试会话"):
            self.f.record(second, self.valid_result(second))
        self.configure()
        job = h.open_job(self.root, NS(stage="test", round=second["round"], transport="native", origin="native-parent"))
        with self.assertRaisesRegex(ValueError, "全新会话"):
            h.bind(self.root, NS(job=job["job"], reviewer="test-reviewer", receipt="合成创建回执"))
        h.bind(self.root, NS(job=job["job"], reviewer="new-retest-context", receipt="另一个合成创建回执"))
        self.assertEqual(self.f.record(second, self.valid_result(second, "new-retest-context"))["status"], "passed")

    def test_new_round_excludes_even_dispatched_unfinished_test_contexts(self):
        self.configure()
        first = self.f.prepare("test")
        job = h.open_job(self.root, NS(stage="test", round=first["round"], transport="native", origin="native-parent"))
        h.bind(self.root, NS(job=job["job"], reviewer="unfinished-test", receipt="合成回执"))
        second = self.f.prepare("test")
        request = ds.load(self.root / second["snapshot"] / "request.json")
        self.assertIn("unfinished-test", request["independentTestPolicy"]["forbiddenSessionIds"])

    def test_fix_record_is_not_mistaken_for_independent_final_acceptance(self):
        with self.assertRaisesRegex(ValueError, "修复不再新建轮次"):
            self.f.prepare("test", kind="fix", method="human")

    def test_same_round_dispatch_retry_needs_a_new_testing_identity(self):
        self.configure()
        prepared = self.f.prepare("test")
        first = h.open_job(self.root, NS(stage="test", round=prepared["round"], transport="native", origin="native-parent"))
        h.bind(self.root, NS(job=first["job"], reviewer="failed-test-context", receipt="合成创建回执"))
        h.fail(self.root, NS(job=first["job"], reason="合成派发失败", receipt="合成失败回执"))
        second = h.open_job(self.root, NS(stage="test", round=prepared["round"], transport="native", origin="native-parent"))
        with self.assertRaisesRegex(ValueError, "重试也必须"):
            h.bind(self.root, NS(job=second["job"], reviewer="failed-test-context", receipt="复用身份"))
        h.bind(self.root, NS(job=second["job"], reviewer="fresh-retry-context", receipt="新会话回执"))
        self.assertEqual(self.f.record(prepared, self.valid_result(prepared, "fresh-retry-context"))["status"], "passed")

    def test_direct_import_cannot_bypass_failed_context_reuse_guard(self):
        self.configure()
        prepared = self.f.prepare("test")
        job = h.open_job(self.root, NS(stage="test", round=prepared["round"], transport="native", origin="native-parent"))
        h.bind(self.root, NS(job=job["job"], reviewer="failed-test-context", receipt="合成创建回执"))
        h.fail(self.root, NS(job=job["job"], reason="合成失败", receipt="合成失败回执"))
        with self.assertRaisesRegex(ValueError, "已失败交接"):
            self.f.record(prepared, self.valid_result(prepared, "failed-test-context"))

    def test_malformed_failed_result_is_rejected_before_persistence(self):
        prepared = self.f.prepare("test")
        value = self.f.result(prepared)
        value.update(overall="fail", independentTest="invalid structure")
        with self.assertRaisesRegex(ValueError, "结构化对象"):
            self.f.record(prepared, value)


if __name__ == "__main__":
    unittest.main()
