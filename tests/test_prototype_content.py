#!/usr/bin/env python3
"""Offline regressions for PRD/prototype binding and traceability integrity."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from build_prototype_v3 import build
from prototype_content import declared_prd_ids, prd_version
from validate_prototype_v3 import extract_manifest, validate


class PrototypeContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ds-prototype-content-")
        self.root = Path(self.tmp.name)
        self.app = self.root / "prototype" / "app"
        (self.app / "pages").mkdir(parents=True)
        (self.app / "specs").mkdir()
        (self.root / "需求").mkdir()
        self.prd = self.root / "需求" / "需求.md"
        self.prd.write_text("""# PRD
## 0. 文档信息
| 字段 | 内容 |
|---|---|
| 当前版本 | v1.0 |
## FR-001：新建任务
## BR-001：标题必填
## PG-001：任务页
## AC-001：创建任务的验收
## FR-002：自动归档
## AC-002：归档业务结果
```markdown
## AC-999：仅供示例，不能作为真实定义
```
""", encoding="utf-8")
        self.config = {
            "schemaVersion": 3,
            "contentStandardVersion": 1,
            "project": {"name": "回归样例", "version": "v1.1", "prd": {"path": "../../需求/需求.md", "version": "v1.0"}},
            "overview": {
                "summary": "测试样例，不代表真实产品", "goals": ["验证绑定与引用"],
                "rules": [{"title": "BR-001", "content": "标题必填，规则来源PRD"}],
                "glossary": [], "changeLogOrder": "newest-first", "prototypeChangeLog": [], "faq": [], "tracking": {"mode": "none"},
                "demo": {"scope": "离线样例，不验证后台", "paths": [{"name": "创建", "pageIds": ["tasks"], "steps": ["打开任务页", "输入标题并提交"]}],
                         "failureTriggers": ["以空标题提交"], "reset": "刷新样例", "persistence": "刷新后不保留"},
            },
            "navigation": [{"id": "docs", "label": "项目文档"}, {"id": "business", "label": "业务"}],
            "pages": [
                {"id": "overview", "kind": "overview", "title": "项目概述", "output": "overview.html", "navGroup": "docs", "businessEnd": "项目文档", "description": "概述", "viewports": {"default": "pc", "supported": [{"type": "pc", "width": 1200, "height": 900}]}},
                {"id": "tasks", "title": "任务页", "output": "tasks.html", "source": "pages/tasks.html", "specs": "specs/tasks.json", "navGroup": "business", "businessEnd": "用户端", "description": "创建任务", "viewports": {"default": "pc", "supported": [{"type": "pc", "width": 1200, "height": 900}]}},
            ],
            "traceability": [
                {"requirementId": "FR-001", "ruleIds": ["BR-001"], "prdPageId": "PG-001", "pageId": "tasks", "moduleKey": "create", "scenario": "创建成功、校验失败", "acceptanceIds": ["AC-001"], "coverage": "covered", "notes": "需真实业务验收"},
                {"requirementId": "FR-002", "ruleIds": [], "pageId": None, "reason": "后台任务", "evidence": "归档结果测试说明", "scenario": "到期归档", "acceptanceIds": ["AC-002"], "coverage": "covered"},
            ],
        }
        self.specs = {"enabled": True, "page": {"title": "页面规范", "sections": []}, "modules": [{"key": "create", "title": "创建", "sections": [{"key": "controls", "title": "内容与控件说明", "type": "controls", "items": [{"name": "创建", "controlType": "按钮", "dataSource": "固定文案", "buttonRole": "save-submit", "validationRules": "标题必填", "failureResult": "提示标题必填", "successResult": "新增任务并显示详情", "note": "提交中禁用；失败保留输入；超时可重试；重复请求复用同一任务；离开可取消等待"}]}]}]}
        (self.app / "pages/tasks.html").write_text('<!doctype html><html><head><title>任务</title></head><body><section data-ds-spec-anchor="create"><button>创建</button></section></body></html>', encoding="utf-8")
        self.write()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        (self.app / "prototype.config.json").write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")
        (self.app / "specs/tasks.json").write_text(json.dumps(self.specs, ensure_ascii=False), encoding="utf-8")

    def build(self):
        output = self.root / "output"
        with contextlib.redirect_stdout(io.StringIO()):
            build(self.app, output)
        return output

    def test_valid_binding_trace_and_standalone_output(self):
        errors, warnings = validate(self.app, None)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        output = self.build()
        errors, warnings = validate(self.app, output)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        manifest = extract_manifest((output / "tasks.html").read_text())
        self.assertEqual(manifest["businessBinding"]["prototypeVersion"], "v1.1")
        self.assertEqual(manifest["businessBinding"]["prd"]["status"], "verified")
        overview_manifest = extract_manifest((output / "overview.html").read_text())
        self.assertEqual(overview_manifest["frameworkFingerprint"], manifest["frameworkFingerprint"])
        self.assertEqual(overview_manifest["buildId"], manifest["buildId"])
        index = (output / "index.html").read_text()
        self.assertIn(f'ds-framework-fingerprint" content="{manifest["frameworkFingerprint"]}', index)
        self.assertIn(f'ds-build-id" content="{manifest["buildId"]}', index)
        self.build()
        rebuilt = extract_manifest((output / "tasks.html").read_text())
        self.assertEqual(manifest["buildId"], rebuilt["buildId"])
        overview = (output / "overview.html").read_text()
        self.assertIn("FR-002", overview)
        self.assertIn("后台任务", overview)
        self.assertIn("演示说明与模拟范围", overview)
        self.assertNotIn("{{TRACEABILITY}}", overview)

    def test_bundled_configuration_and_spec_examples_build_together(self):
        assets = Path(__file__).resolve().parent.parent / "skills/dev-sequence/assets/prototype-framework"
        self.config = json.loads((assets / "prototype.config.example.json").read_text())
        self.prd.write_text(self.prd.read_text().replace("v1.0", "v0.1"))
        self.write()
        (self.app / "specs/overview.json").write_text('{"enabled":false}')
        (self.app / "specs/example-list.json").write_text((assets / "spec.example.json").read_text())
        for page in self.config["pages"]:
            if page.get("source"):
                content = '<section data-ds-spec-anchor="batch-actions">示例模块</section>' if page["id"] == "example-list" else '<main>说明页</main>'
                (self.app / page["source"]).write_text('<!doctype html><html><head><title>示例</title></head><body>' + content + '</body></html>')
        errors, warnings = validate(self.app, None)
        self.assertEqual(errors, [])
        self.assertTrue(any("partial" in warning for warning in warnings))
        output = self.build()
        errors, _ = validate(self.app, output)
        self.assertEqual(errors, [])

    def test_references_must_be_real_definitions(self):
        self.config["traceability"][0]["acceptanceIds"] = ["AC-999"]
        self.write()
        errors, _ = validate(self.app, None)
        self.assertTrue(any("AC-999" in error and "not declared" in error for error in errors))
        self.assertNotIn("AC-999", declared_prd_ids(self.prd.read_text()))

    def test_unknown_page_and_module_are_rejected(self):
        for field, value in (("pageId", "missing-page"), ("moduleKey", "missing-module")):
            original = self.config["traceability"][0][field]
            self.config["traceability"][0][field] = value
            self.write()
            errors, _ = validate(self.app, None)
            self.assertTrue(any(field in error for error in errors), errors)
            self.config["traceability"][0][field] = original

    def test_prd_version_mismatch_and_unreadable_prd_are_rejected(self):
        self.config["project"]["prd"]["version"] = "v0.9"
        self.write()
        errors, _ = validate(self.app, None)
        self.assertTrue(any("does not match PRD current version" in error for error in errors))
        self.config["project"]["prd"]["version"] = "v1.0"
        self.prd.unlink()
        self.write()
        errors, _ = validate(self.app, None)
        self.assertTrue(any("not checked" in error for error in errors))
        with self.assertRaises(ValueError):
            self.build()

    def test_legacy_migration_is_explicit_and_strict_mode_is_available(self):
        del self.config["contentStandardVersion"]
        del self.config["project"]["prd"]
        del self.config["project"]["version"]
        del self.config["traceability"]
        del self.config["overview"]["demo"]
        self.write()
        errors, warnings = validate(self.app, None)
        self.assertEqual(errors, [])
        self.assertTrue(any("Legacy content contract" in warning for warning in warnings))
        self.assertTrue(any("not checked" in warning for warning in warnings))
        errors, _ = validate(self.app, None, strict_content=True)
        self.assertTrue(errors)

    def test_bound_prd_or_source_changes_invalidate_built_output(self):
        output = self.build()
        self.prd.write_text(self.prd.read_text() + "\n业务规则说明已修订。\n")
        errors, _ = validate(self.app, output)
        self.assertTrue(any("businessBinding" in error for error in errors))
        self.assertTrue(any("rebuild is required" in error for error in errors))
        output = self.build()
        self.config["traceability"][0]["notes"] = "映射说明已改变"
        self.write()
        errors, _ = validate(self.app, output)
        self.assertTrue(any("buildId does not match current" in error for error in errors))

    def test_non_ui_mapping_requires_other_verification_and_no_fake_module(self):
        self.config["traceability"][1].pop("evidence")
        self.config["traceability"][1]["moduleKey"] = "create"
        self.write()
        errors, _ = validate(self.app, None)
        self.assertTrue(any("no-UI mapping requires" in error for error in errors))
        self.assertTrue(any("cannot reference a UI module" in error for error in errors))

    def test_new_standard_submit_controls_include_recovery_description(self):
        self.specs["modules"][0]["sections"][0]["items"][0].pop("note")
        self.write()
        errors, _ = validate(self.app, None)
        self.assertTrue(any("submission lifecycle" in error for error in errors))

    def test_version_metadata_is_read_from_current_document_not_code_examples(self):
        self.assertEqual(prd_version(self.prd.read_text()), "v1.0")
        self.assertEqual(prd_version('> 版本：V2.1｜日期：2026-10-23'), "V2.1")
        self.assertIsNone(prd_version('```markdown\n| 当前版本 | v9.9 |\n```'))
        self.assertIsNone(prd_version('| 版本 | 日期 |\n|---|---|\n| v1.0 | 2026-10-23 |'))
        self.assertIsNone(prd_version('````markdown\n```text\n| 当前版本 | v9.9 |\n```\n````'))


if __name__ == "__main__":
    unittest.main()
