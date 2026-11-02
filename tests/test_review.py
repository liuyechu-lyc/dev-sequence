"""Behavioral review regressions, with synthetic reviewers, no models/network."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import ds
import review_records as records
import review_choice as choices


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ds-review-")
        self.root = Path(self.tmp.name).resolve()
        (self.root / "baseline.md").write_text("# 测试输入\n权限：测试账号只能访问自己的记录。\n", encoding="utf-8")
        (self.root / "output.md").write_text("# 测试产物\n声明结果仅用于自动化回归。\n", encoding="utf-8")
        ds.initialize(self.root, NS(stages=",".join(ds.STAGES), name="回归测试，不是业务验收"))

    def tearDown(self):
        self.tmp.cleanup()

    def spec(self, stage="prd"):
        return {"artifacts": [{"path": "output.md", "version": "v1"}], "context": [{"role": role, "path": "baseline.md", "version": "v1"} for role in ds.STAGES[stage][2]], "scope": {"description": "自动化工具回归，不代表真实业务验证", "exclusions": []}, "checklist": [{"id": "CHECK-1", "text": "测试检查项", "kind": "semantic"}]}

    def prepare(self, stage="prd", kind="review", method="agent", spec=None, **limits):
        path = self.root / "request-source.json"
        ds.json_write(path, spec or self.spec(stage))
        args = NS(stage=stage, kind=kind, method=method, spec=path, producer_session="test-producer", max_files=limits.get("max_files", 500), max_chars=limits.get("max_chars", 400000))
        if kind == "review" and method != "script":
            choices.choose(self.root, NS(stages=stage, method="native" if method == "agent" else "third-party",
                           reuse="stage", by="测试桩", source="合成选择，仅测试", text="测试明确选择，不代表实际用户"))
        return ds.prepare(self.root, args)

    def result(self, prepared):
        return {"stage": prepared["stage"], "round": prepared["round"], "inputFingerprint": prepared["inputFingerprint"], "overall": "pass", "reviewer": {"name": "自动化测试桩，非真实Agent", "freshContext": True, "isolationEvidence": "仅测试隔离字段校验，不声称调用了外部Agent", "sessionId": "test-reviewer"}, "items": [{"id": "CHECK-1", "result": "pass", "evidence": "测试桩给出的合成证据，仅验证工具状态机"}], "issues": [], "summary": "合成结果，只用于工具回归", "notChecked": []}

    def test_an_old_round_result_cannot_be_relabelled_as_new_review(self):
        first = self.prepare()
        self.record(first)
        second = self.prepare()
        self.assertEqual(first["inputFingerprint"], second["inputFingerprint"])
        with self.assertRaisesRegex(ValueError, "阶段或轮次"):
            self.record(second, self.result(first))

    def record(self, prepared, result=None):
        path = self.root / "result.json"
        ds.json_write(path, result or self.result(prepared))
        return ds.record(self.root, NS(stage=prepared["stage"], round=prepared["round"], result=path))

    def status(self, stage="prd"):
        db = ds.database(self.root)
        ds.refresh(self.root, db)
        return db["stages"][stage]

    def test_all_six_stages_can_prepare_from_equivalent_external_inputs(self):
        for stage, (node, _, _) in ds.STAGES.items():
            prepared = self.prepare(stage)
            self.assertTrue((self.root / prepared["prompt"]).is_file())
            self.assertTrue((self.root / node / ".review-skill.md").is_file())
            self.assertTrue((self.root / node / "验收规则.html").is_file())
            self.assertFalse(list((self.root / node).glob("验收报告*")))
            snapshot = self.root / prepared["snapshot"]
            manifest = ds.load(snapshot / "manifest.json")
            self.assertTrue(any(m["role"] == "review-standard" for m in manifest["inputs"]))
            self.assertEqual((snapshot / "files/output.md").read_bytes(), (self.root / "output.md").read_bytes())

    def test_equivalent_inputs_do_not_skip_missing_required_roles(self):
        spec = self.spec("code")
        spec["context"] = []
        with self.assertRaisesRegex(ValueError, "必要上下文"):
            self.prepare("code", spec=spec)

    def test_legitimate_non_ui_roles_are_explicit(self):
        spec = self.spec("tech")
        spec["context"][-1] = {"role": "prototype", "notApplicable": True, "reason": "实际为无界面命令行需求"}
        self.prepare("tech", spec=spec)
        spec["context"][-1]["path"] = "missing.html"
        with self.assertRaisesRegex(ValueError, "不适用"):
            self.prepare("tech", spec=spec)

    def test_empty_and_partial_results_cannot_pass(self):
        prepared = self.prepare()
        result = self.result(prepared)
        result["items"] = []
        with self.assertRaisesRegex(ValueError, "逐项"):
            self.record(prepared, result)
        result = self.result(prepared)
        result["items"][0]["result"] = "not_checked"
        self.assertEqual(self.record(prepared, result)["status"], "pending")

    def test_unknown_fingerprint_is_rejected(self):
        prepared = self.prepare()
        result = self.result(prepared)
        result["inputFingerprint"] = "wrong"
        with self.assertRaisesRegex(ValueError, "指纹"):
            self.record(prepared, result)

    def test_agent_requires_new_context_and_different_known_session(self):
        prepared = self.prepare()
        result = self.result(prepared)
        result["reviewer"]["freshContext"] = False
        with self.assertRaisesRegex(ValueError, "新上下文"):
            self.record(prepared, result)
        result = self.result(prepared)
        result["reviewer"]["sessionId"] = "test-producer"
        with self.assertRaisesRegex(ValueError, "会话相同"):
            self.record(prepared, result)

    def test_fixed_but_unverified_major_issue_blocks_pass(self):
        prepared = self.prepare()
        result = self.result(prepared)
        result["issues"] = [{"id": "PRD-I001", "severity": "major", "status": "fixed", "description": "测试问题", "source": "output.md", "evidence": "测试证据"}]
        self.assertEqual(self.record(prepared, result)["status"], "changes-requested")

    def test_fix_round_never_becomes_passed(self):
        with self.assertRaisesRegex(ValueError, "修复不再新建轮次"):
            self.prepare(kind="fix")
        self.assertEqual(len(ds.database(self.root)["stages"]["prd"]["rounds"]), 0)

    def test_reports_are_frozen_and_summary_contains_same_result(self):
        prepared = self.prepare()
        output = self.record(prepared)
        report = self.root / output["report"]
        original = report.read_bytes()
        db = ds.database(self.root)
        ds.save(self.root, db)
        self.assertEqual(report.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "冻结报告"):
            self.record(prepared)
        md = report.with_suffix(".md").read_text(encoding="utf-8")
        html = report.read_text(encoding="utf-8")
        self.assertIn("ds-review-data", html)
        self.assertIn("合成结果", (self.root / "验收记录/验收记录总.md").read_text())

    def test_reverification_can_freeze_a_specific_prior_report_as_context(self):
        prepared = self.prepare()
        self.record(prepared)
        spec = self.spec()
        spec["context"].append({"role": "prior-review", "path": "验收记录/需求验收记录/.过程/第001轮/原始验收报告.json", "version": "r001"})
        recheck = self.prepare(spec=spec)
        inputs = ds.load(self.root / recheck["snapshot"] / "manifest.json")["inputs"]
        self.assertTrue(any(i.get("role") == "prior-review" for i in inputs))

    def test_upstream_change_selectively_invalidates_dependent_review(self):
        prd = self.prepare("prd")
        tech = self.prepare("tech")
        self.record(prd)
        self.record(tech)
        (self.root / "baseline.md").write_text("上游已变化", encoding="utf-8")
        self.assertEqual(self.status("prd")["rounds"][-1]["status"], "passed")
        self.assertEqual(self.status("tech")["rounds"][-1]["status"], "stale")

    def test_current_rules_change_invalidates_and_preserves_project_customizations(self):
        prepared = self.prepare()
        self.record(prepared)
        rules = self.root / "需求/.review-skill.md"
        rules.write_text(rules.read_text() + "\n项目额外规则\n")
        ds.rules(self.root, "prd")
        self.assertIn("项目额外规则", rules.read_text())
        self.assertEqual(self.status()["rounds"][-1]["status"], "stale")

    def test_change_before_import_cannot_pass(self):
        prepared = self.prepare()
        (self.root / "output.md").write_text("当前产物已变化")
        self.assertEqual(self.record(prepared)["status"], "stale")

    def test_snapshot_or_prompt_tampering_invalidates(self):
        prepared = self.prepare()
        (self.root / prepared["prompt"]).write_text("被修改的提示词")
        self.assertEqual(self.record(prepared)["status"], "stale")

    def test_binary_is_snapshotted_without_claiming_text_inspection(self):
        (self.root / "image.png").write_bytes(b"\x89PNG\x00\xff")
        spec = self.spec()
        spec["artifacts"] = [{"path": "image.png", "version": "v1"}]
        prepared = self.prepare(spec=spec)
        manifest = ds.load(self.root / prepared["snapshot"] / "manifest.json")
        self.assertEqual(manifest["inputs"][0]["kind"], "binary")

    def test_file_limits_do_not_silently_truncate(self):
        with self.assertRaisesRegex(ValueError, "超限"):
            self.prepare(max_chars=1)

    def test_excluding_every_artifact_cannot_pass(self):
        spec = self.spec()
        spec["scope"]["exclusions"] = [{"path": "output.md", "reason": "测试排除全部"}]
        with self.assertRaisesRegex(ValueError, "全部排除"):
            self.prepare(spec=spec)

    def test_path_escape_and_symlink_are_rejected(self):
        spec = self.spec()
        spec["artifacts"][0]["path"] = "../outside.md"
        with self.assertRaisesRegex(ValueError, "越出项目"):
            self.prepare(spec=spec)
        (self.root / "alias.md").symlink_to(self.root / "output.md")
        spec["artifacts"][0]["path"] = "alias.md"
        with self.assertRaisesRegex(ValueError, "符号链接"):
            self.prepare(spec=spec)

    def test_waiver_is_separate_and_needs_real_basis(self):
        prepared = self.prepare()
        result = self.result(prepared)
        result["overall"] = "waived"
        with self.assertRaisesRegex(ValueError, "豁免"):
            self.record(prepared, result)
        result["waiver"] = {"reason": "回归分支测试", "approvedBy": "测试桩", "evidence": "仅合成测试"}
        self.assertEqual(self.record(prepared, result)["status"], "waived")

    def test_confirmation_is_separate_and_invalidates_with_baseline(self):
        prepared = self.prepare()
        self.record(prepared)
        self.assertEqual(self.status()["confirmation"]["status"], "pending")
        ds.confirm(self.root, NS(stage="prd", by="测试确认桩", evidence="合成授权", decision="accepted", mode="manual", accept_waiver=False))
        self.assertEqual(self.status()["confirmation"]["status"], "accepted")
        (self.root / "output.md").write_text("变化")
        self.assertEqual(self.status()["confirmation"]["status"], "stale")

    def test_script_cannot_complete_semantic_gate(self):
        prepared = self.prepare(method="script")
        self.assertEqual(self.record(prepared)["status"], "pending")

    def test_automated_scope_pass_still_cannot_confirm_entire_stage(self):
        spec = self.spec()
        spec["checklist"][0]["kind"] = "automated"
        prepared = self.prepare(method="script", spec=spec)
        self.assertEqual(self.record(prepared)["status"], "passed")
        with self.assertRaisesRegex(ValueError, "纯脚本"):
            ds.confirm(self.root, NS(stage="prd", by="测试", evidence="测试", decision="accepted", mode="manual", accept_waiver=False))

    def test_lock_prevents_parallel_summary_writes(self):
        with ds.locked(self.root):
            with self.assertRaisesRegex(ValueError, "写入占用"):
                with ds.locked(self.root):
                    pass
        self.assertFalse((self.root / ".dev-sequence/write.lock").exists())

    def test_html_never_executes_report_content(self):
        rendered = ds.render("# <script>alert(1)</script>", "测试", {"x": "</script><script>alert(2)</script>"})
        self.assertNotIn("<script>alert", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("\\u003c/script>", rendered)

    def test_tasks_reject_cycles_and_unsubstantiated_completion(self):
        rows = [{"id": "T1", "description": "测试", "sourceRefs": ["FR-1"], "outputs": ["x.py"], "doneWhen": "测试条件", "validation": "测试方法", "state": "todo", "dependsOn": ["T2"]}, {"id": "T2", "description": "测试", "sourceRefs": ["FR-1"], "outputs": ["y.py"], "doneWhen": "测试条件", "validation": "测试方法", "state": "todo", "dependsOn": ["T1"]}]
        ds.json_write(self.root / "tasks.json", {"tasks": rows})
        with self.assertRaisesRegex(ValueError, "存在环"):
            ds.tasks(self.root, NS(source="tasks.json"))
        rows[0]["dependsOn"] = []
        rows[0]["state"] = "verified"
        ds.json_write(self.root / "tasks.json", {"tasks": rows})
        with self.assertRaisesRegex(ValueError, "证据"):
            ds.tasks(self.root, NS(source="tasks.json"))


if __name__ == "__main__":
    unittest.main()
