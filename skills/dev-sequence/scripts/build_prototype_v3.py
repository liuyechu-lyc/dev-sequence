#!/usr/bin/env python3
"""Build standalone Dev Sequence v3 prototypes from project data and business pages."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
from pathlib import Path

from prototype_content import prd_binding


FRAMEWORK_VERSION = "3.14.0"
PROTOCOL_VERSION = 5
SPEC_SCHEMA_VERSION = 5
MANAGED_RE = re.compile(r"\n?<!-- DS-FRAMEWORK-START -->.*?<!-- DS-FRAMEWORK-END -->\n?", re.S)


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def framework_assets() -> tuple[str, str, str, str, str]:
    root = Path(__file__).resolve().parent.parent / "assets" / "prototype-framework"
    return (
        (root / "index.html").read_text(encoding="utf-8"),
        (root / "page-runtime.css").read_text(encoding="utf-8"),
        (root / "page-runtime.js").read_text(encoding="utf-8"),
        (root / "overview-template.html").read_text(encoding="utf-8"),
        (root / "overview.css").read_text(encoding="utf-8"),
    )


def framework_fingerprint(
    index_template: str,
    page_css: str,
    page_js: str,
    overview_template: str,
    overview_css: str,
) -> str:
    payload = "\n".join((index_template, page_css, page_js, overview_template, overview_css)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def prototype_build_id(
    source_dir: Path,
    config: dict,
    index_template: str,
    page_css: str,
    page_js: str,
    overview_template: str,
    overview_css: str,
) -> str:
    """Return a deterministic project build id from every effective build input."""
    digest = hashlib.sha256()

    def add(label: str, payload: bytes) -> None:
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")

    add("framework-version", FRAMEWORK_VERSION.encode("utf-8"))
    add("builder", Path(__file__).read_bytes())
    add("content-helper", Path(__file__).with_name("prototype_content.py").read_bytes())
    binding, prd_text = prd_binding(source_dir, config)
    if prd_text is not None:
        add("bound-prd", prd_text.encode("utf-8"))
    add(
        "prototype.config.json",
        json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )
    add("framework/index.html", index_template.encode("utf-8"))
    add("framework/page-runtime.css", page_css.encode("utf-8"))
    add("framework/page-runtime.js", page_js.encode("utf-8"))
    add("framework/overview-template.html", overview_template.encode("utf-8"))
    add("framework/overview.css", overview_css.encode("utf-8"))
    referenced_paths = {
        str(page[field])
        for page in config.get("pages", [])
        for field in ("source", "specs")
        if page.get(field)
    }
    for relative_path in sorted(referenced_paths):
        add(relative_path, (source_dir / relative_path).read_bytes())
    return digest.hexdigest()[:12]


def viewport_manifest(page: dict) -> dict:
    viewports = page.get("viewports") or {}
    supported = viewports.get("supported") or []
    return {"default": viewports.get("default"), "supported": supported}


def specs_with_generated_viewports(page: dict, specs: dict) -> dict:
    """Expose the registry viewport declaration in page-level specifications."""
    if specs.get("enabled") is False:
        return specs
    result = json.loads(json.dumps(specs, ensure_ascii=False))
    viewports = viewport_manifest(page)
    labels = {"pc": "PC", "tablet": "平板", "mobile": "手机"}
    descriptions = []
    for viewport in viewports["supported"]:
        label = labels.get(viewport["type"], viewport["type"])
        default_suffix = "，默认" if viewport["type"] == viewports["default"] else ""
        descriptions.append(f"{label}（{viewport['width']} × {viewport['height']}{default_suffix}）")
    generated = {
        "key": "supported-viewports",
        "title": "兼容终端",
        "content": "、".join(descriptions),
        "changeType": "existing",
        "generated": True,
    }
    page_spec = result.setdefault("page", {"title": "页面技术规范", "sections": []})
    sections = page_spec.setdefault("sections", [])
    page_spec["sections"] = [generated] + [
        section for section in sections if section.get("key") != "supported-viewports"
    ]
    return result


def page_manifest(page: dict, specs: dict, fingerprint: str, build_id: str, binding: dict | None = None) -> dict:
    return {
        "channel": "dev-sequence-prototype",
        "protocolVersion": PROTOCOL_VERSION,
        "frameworkVersion": FRAMEWORK_VERSION,
        "specSchemaVersion": SPEC_SCHEMA_VERSION,
        "generatedBy": "dev-sequence",
        "frameworkFingerprint": fingerprint,
        "buildId": build_id,
        "businessBinding": binding or {},
        "pageId": page["id"],
        "title": page["title"],
        "changeType": page.get("changeType", "existing"),
        "changeImpact": page.get("changeImpact", "none"),
        "viewports": viewport_manifest(page),
        "capabilities": {
            "specs": specs.get("enabled", True),
            "markers": specs.get("enabled", True),
            "dynamicHeight": True,
            "responsiveViewport": len(viewport_manifest(page)["supported"]) > 1,
        },
        "specs": specs,
    }


def inject_cache_meta(source_html: str) -> str:
    if not re.search(r"</head>", source_html, re.I):
        raise ValueError("business page must contain a closing </head> tag")
    missing = []
    for http_equiv, content in (
        ("Cache-Control", "no-cache, no-store, must-revalidate"),
        ("Pragma", "no-cache"),
        ("Expires", "0"),
    ):
        if not re.search(rf'<meta\s+http-equiv=["\']{re.escape(http_equiv)}["\']', source_html, re.I):
            missing.append(f'<meta http-equiv="{http_equiv}" content="{content}">')
    if not missing:
        return source_html
    return re.sub(r"</head>", lambda _: "\n".join(missing) + "\n</head>", source_html, count=1, flags=re.I)


def inject_framework(source_html: str, manifest: dict, page_css: str, page_js: str) -> str:
    clean = MANAGED_RE.sub("\n", source_html)
    clean = inject_cache_meta(clean)
    if "</body>" not in clean.lower():
        raise ValueError("business page must contain a closing </body> tag")
    managed = f"""
<!-- DS-FRAMEWORK-START -->
<style id="pdFrameworkStyles">{page_css}</style>
<div class="ds-spec-marker-layer ds-base" id="pdBaseMarkerLayer" aria-label="页面技术规范标注"></div>
<div class="ds-overlay-marker-host" id="pdOverlayMarkerHost" aria-label="浮层技术规范标注"></div>
<button class="ds-back-to-frame" id="pdBackToFrame" type="button">在框架中打开</button>
<script id="prototype-manifest" type="application/json">{json_script(manifest)}</script>
<script id="pdFrameworkRuntime">{page_js}</script>
<!-- DS-FRAMEWORK-END -->
"""
    return re.sub(r"</body>", lambda _: managed + "</body>", clean, count=1, flags=re.I)


def nav_config(config: dict) -> dict:
    groups = []
    page_by_group: dict[str, list[dict]] = {}
    for page in config["pages"]:
        page_by_group.setdefault(page["navGroup"], []).append(page)
    for group in config["navigation"]:
        items = []
        for page in page_by_group.get(group["id"], []):
            item = {
                "id": page["id"],
                "label": page["title"],
                "file": page["output"],
                "kind": page.get("kind", "business"),
            }
            items.append(item)
        if items:
            groups.append({"label": group["label"], "pages": items})
    return {"groups": groups}


def overview_change_refs(items: list[dict]) -> str:
    action_classes = {"新增": "new", "修改": "modified", "删除": "deleted"}
    return "".join(
        f"<span class=\"change-ref\"><span class=\"change-ref-name\">{html.escape(item['name'])}</span>"
        f"<span class=\"op-tag {action_classes[item['action']]}\">{html.escape(item['action'])}</span></span>"
        for item in items
    )


def overview_change_rowspans(items: list[dict]) -> list[dict[str, int]]:
    """Calculate hierarchical consecutive row spans without reordering source data."""
    spans: list[dict[str, int]] = [{} for _ in items]
    fields = (
        ("version", lambda item: (item["version"],)),
        ("datetime", lambda item: (item["version"], item["datetime"])),
        ("terminal", lambda item: (item["version"], item["datetime"], item["terminal"])),
    )
    for field, key_for in fields:
        index = 0
        while index < len(items):
            key = key_for(items[index])
            end = index + 1
            while end < len(items) and key_for(items[end]) == key:
                end += 1
            spans[index][field] = end - index
            index = end
    return spans


def overview_change_rows(items: list[dict]) -> str:
    spans = overview_change_rowspans(items)
    rows = []
    for index, item in enumerate(items):
        cells = []
        for field in ("version", "datetime", "terminal"):
            if field in spans[index]:
                cells.append(
                    f"<td rowspan=\"{spans[index][field]}\" data-change-batch-field=\"{field}\">"
                    f"{html.escape(item[field])}</td>"
                )
        row_class = " class=\"change-batch-start\"" if "version" in spans[index] else ""
        rows.append(
            f"<tr{row_class} data-change-version=\"{html.escape(item['version'])}\">"
            f"{''.join(cells)}<td>{overview_change_refs(item['pages'])}</td>"
            f"<td>{overview_change_refs(item['modules'])}</td>"
            f"<td>{html.escape(item['summary'])}</td></tr>"
        )
    return "".join(rows)


def overview_html(config: dict, template: str, stylesheet: str, binding: dict | None = None) -> str:
    project = config["project"]
    overview = config["overview"]
    binding = binding or {"prototypeVersion": project.get("version"), "prd": project.get("prd", {})}
    prd = binding.get("prd") or {}
    status_labels = {"verified": "构建时版本已核对", "mismatch": "版本不一致", "unverified": "尚未核对"}
    binding_html = (
        f"<p>原型业务版本：{html.escape(str(binding.get('prototypeVersion') or '未声明'))}</p>"
        f"<p>关联 PRD：{html.escape(str(prd.get('path') or '未声明'))} · "
        f"{html.escape(str(prd.get('version') or '未声明版本'))} · "
        f"{status_labels.get(prd.get('status'), '尚未核对')}</p>"
    )
    demo = overview.get("demo") or {}
    if demo:
        paths_html = "".join(
            f"<li><b>{html.escape(item['name'])}</b><ol>"
            + "".join(f"<li>{html.escape(step)}</li>" for step in item.get("steps", []))
            + "</ol></li>" for item in demo.get("paths", [])
        )
        failure_html = "".join(f"<li>{html.escape(item)}</li>" for item in demo.get("failureTriggers", []))
        if not failure_html:
            failure_html = f"<li>{html.escape(demo.get('failureNotApplicableReason', '未声明失败触发方式'))}</li>"
        demo_html = (
            f"<p><b>模拟范围：</b>{html.escape(demo.get('scope', '未声明'))}</p>"
            f"<ul>{paths_html}</ul><p><b>失败触发：</b></p><ul>{failure_html}</ul>"
            f"<p><b>重置方式：</b>{html.escape(demo.get('reset', '未声明'))}</p>"
            f"<p><b>数据保留：</b>{html.escape(demo.get('persistence', '未声明'))}</p>"
        )
    else:
        demo_html = '<div class="empty-state">尚未补充演示路径、模拟边界与重置说明；不代表已完成功能验收</div>'
    page_by_id = {page["id"]: page for page in config["pages"]}
    trace_rows = []
    coverage_labels = {"covered": "设计已覆盖", "partial": "部分覆盖", "pending": "待补充", "not-applicable": "不适用"}
    for row in config.get("traceability") or []:
        page = page_by_id.get(row.get("pageId"))
        if page:
            location = html.escape(page["title"])
            if row.get("moduleKey"):
                location += " / " + html.escape(row["moduleKey"])
        else:
            location = "无独立界面：" + html.escape(row.get("reason", "未说明"))
        trace_rows.append(
            "<tr>" + "".join(f"<td>{value}</td>" for value in (
                html.escape(row["requirementId"]),
                html.escape("、".join(row.get("ruleIds", [])) or "—"),
                location,
                html.escape(row.get("scenario", "")),
                html.escape("、".join(row.get("acceptanceIds", []))),
                html.escape(coverage_labels.get(row.get("coverage"), "待核对") + "；" + row.get("notes", row.get("evidence", ""))),
            )) + "</tr>"
        )
    traceability_html = (
        '<p>下表说明需求设计覆盖情况，实际业务结果仍需测试验证。</p>'
        '<table><thead><tr><th>需求</th><th>规则</th><th>原型位置</th><th>场景/状态</th><th>验收条件</th><th>覆盖/待决情况</th></tr></thead>'
        f"<tbody>{''.join(trace_rows)}</tbody></table>"
    ) if trace_rows else '<div class="empty-state">尚未提供需求追溯映射，需求覆盖未检查</div>'
    business_pages = [
        page for page in config["pages"]
        if page.get("kind") not in {"overview", "component-guide", "diagram-guide"}
    ]
    guide_pages = {
        "component-guide": [page for page in config["pages"] if page.get("kind") == "component-guide"],
        "diagram-guide": [page for page in config["pages"] if page.get("kind") == "diagram-guide"],
    }
    ends: list[str] = []
    for page in business_pages:
        if page["businessEnd"] not in ends:
            ends.append(page["businessEnd"])
    page_collections: list[tuple[str, list[dict], str]] = [
        (business_end, [page for page in business_pages if page["businessEnd"] == business_end], "business")
        for business_end in ends
    ]
    navigation_labels = {
        group.get("id"): group.get("label", "")
        for group in config.get("navigation", [])
    }
    default_guide_labels = {
        "component-guide": "原型控件说明",
        "diagram-guide": "项目图解",
    }
    for guide_kind, pages in guide_pages.items():
        if pages:
            guide_group_label = navigation_labels.get(
                pages[0].get("navGroup"),
                default_guide_labels[guide_kind],
            )
            page_collections.append((guide_group_label, pages, guide_kind))

    goals = "".join(f"<li>{html.escape(item)}</li>" for item in overview.get("goals", []))
    rules = "".join(
        f"<article class=\"rule\"><b>{html.escape(item['title'])}</b><p>{html.escape(item['content'])}</p></article>"
        for item in overview.get("rules", [])
    )
    glossary = "".join(
        f"<article class=\"term\"><b>{html.escape(item['term'])}</b><p>{html.escape(item['definition'])}</p></article>"
        for item in overview.get("glossary", [])
    ) or "<div class=\"empty-state\">暂无需要解析的核心名词</div>"
    page_groups = []
    for business_end, pages, page_kind in page_collections:
        is_guide_group = page_kind != "business"
        changed = [page for page in pages if page.get("changeType") in {"new", "modified"}]
        change_count = sum(len(page.get("versionChanges", [])) for page in pages)
        rows = []
        for page in pages:
            status = page.get("changeType", "existing")
            status_badge = ""
            if status in {"new", "modified"}:
                label = "本次新增" if status == "new" else "本次修改"
                status_badge = f"<span class=\"tag\">{label}</span>"
            changes = page.get("versionChanges") or []
            change_html = "".join(f"<span class=\"change-point\" data-change-point>{html.escape(item)}</span>" for item in changes) or "本版本无修改"
            rows.append(
                f"<tr data-page-id=\"{html.escape(page['id'])}\" data-change-type=\"{status}\">"
                f"<td>{html.escape(page['title'])}{status_badge}</td>"
                f"<td>{html.escape(page['description'])}</td><td>{change_html}</td></tr>"
            )
        key = re.sub(r"[^a-z0-9-]", "-", business_end.lower()) or "business"
        page_groups.append(
            f"<article class=\"page-group{' ' + page_kind + '-group' if is_guide_group else ''}\" "
            f"data-overview-group=\"{html.escape(key)}\" data-page-kind=\"{page_kind}\">"
            f"<header class=\"group-head\" data-overview-group-header><h2>{html.escape(business_end)}</h2>"
            f"<div class=\"stats\"><span>{'说明页总数' if is_guide_group else '页面总数'} <strong data-stat=\"total-pages\">{len(pages)}</strong></span>"
            f"<span>本次新增/修改 <strong data-stat=\"changed-pages\">{len(changed)}</strong></span>"
            f"<span>设计修改点 <strong data-stat=\"change-points\">{change_count}</strong></span></div></header>"
            "<table class=\"page-table\"><thead><tr><th>页面</th><th>页面功能描述</th><th>本版本修改内容</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></article>"
        )

    prototype_change_rows = overview_change_rows(overview.get("prototypeChangeLog", []))
    if prototype_change_rows:
        prototype_change_html = (
            "<table class=\"change-log-table\"><thead><tr><th>版本</th><th>日期时间</th><th>终端</th><th>涉及页面</th>"
            "<th>涉及模块</th><th>修改内容概述</th></tr></thead>"
            f"<tbody>{prototype_change_rows}</tbody></table>"
        )
    else:
        prototype_change_html = (
            "<table class=\"change-log-table\"><thead><tr><th>版本</th><th>日期时间</th><th>终端</th><th>涉及页面</th>"
            "<th>涉及模块</th><th>修改内容概述</th></tr></thead>"
            "<tbody><tr><td colspan=\"6\"><div class=\"empty-state\">暂无经作者确认写入的原型修改记录</div></td></tr></tbody></table>"
        )

    faq_rows = "".join(
        f"<tr><td>{html.escape(item['id'])}</td><td>{html.escape(item['raisedAt'])}</td>"
        f"<td>{html.escape(item['role'])}<br>{html.escape(item.get('scope', ''))}</td>"
        f"<td>{html.escape(item['question'])}</td><td>{html.escape(item.get('answer', '待产品确认'))}</td>"
        f"<td>{html.escape(item['status'])}</td></tr>"
        for item in overview.get("faq", [])
    )
    if faq_rows:
        faq_html = (
            "<table class=\"faq-table\"><thead><tr><th>编号</th><th>提出时间</th><th>提出角色/涉及范围</th>"
            "<th>疑问</th><th>产品答复/结论</th><th>状态</th></tr></thead>"
            f"<tbody>{faq_rows}</tbody></table>"
        )
    else:
        faq_html = (
            "<table class=\"faq-table\"><thead><tr><th>编号</th><th>提出时间</th><th>提出角色/涉及范围</th>"
            "<th>疑问</th><th>产品答复/结论</th><th>状态</th></tr></thead>"
            "<tbody><tr><td colspan=\"6\"><div class=\"empty-state\">暂无研发、测试提出的 FAQ 记录</div></td></tr></tbody></table>"
        )

    tracking = overview.get("tracking") or {"mode": "none"}
    if tracking.get("mode") == "url":
        tracking_html = f"<a href=\"{html.escape(tracking['url'])}\" target=\"_blank\" rel=\"noopener noreferrer\">埋点文档</a>"
    else:
        tracking_html = "本需求无需埋点"

    values = {
        "PAGE_TITLE": f"{html.escape(project['name'])} · 项目概述",
        "OVERVIEW_CSS": stylesheet,
        "PROJECT_NAME": html.escape(project["name"]),
        "PROJECT_SUBTITLE": html.escape(project.get("subtitle", "")),
        "BUSINESS_BINDING": binding_html,
        "DEMO": demo_html,
        "TRACEABILITY": traceability_html,
        "SUMMARY": html.escape(overview["summary"]),
        "GOALS": goals,
        "GLOSSARY": glossary,
        "RULES": rules,
        "PAGE_GROUPS": "".join(page_groups),
        "CHANGE_LOG": prototype_change_html,
        "FAQ": faq_html,
        "TRACKING_MODE": html.escape(tracking.get("mode", "none")),
        "TRACKING": tracking_html,
    }
    result = template
    for name, value in values.items():
        result = result.replace("{{" + name + "}}", value)
    unresolved = sorted(set(re.findall(r"{{([A-Z0-9_]+)}}", result)))
    if unresolved:
        raise ValueError(f"overview template has unresolved placeholders: {', '.join(unresolved)}")
    return result


def build(source_dir: Path, output_dir: Path) -> None:
    from validate_prototype_v3 import validate
    errors, warnings = validate(source_dir, None)
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        raise ValueError("Source validation failed:\n" + "\n".join(errors))
    config = read_json(source_dir / "prototype.config.json")
    binding, _ = prd_binding(source_dir, config)
    index_template, page_css, page_js, overview_template, overview_css = framework_assets()
    fingerprint = framework_fingerprint(index_template, page_css, page_js, overview_template, overview_css)
    build_id = prototype_build_id(
        source_dir,
        config,
        index_template,
        page_css,
        page_js,
        overview_template,
        overview_css,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    for page in config["pages"]:
        specs_path = source_dir / page["specs"] if page.get("specs") else None
        specs = read_json(specs_path) if specs_path else {"enabled": False}
        if page.get("kind") == "overview":
            source = overview_html(config, overview_template, overview_css, binding)
        else:
            source = (source_dir / page["source"]).read_text(encoding="utf-8")
        manifest = page_manifest(page, specs_with_generated_viewports(page, specs), fingerprint, build_id, binding)
        result = inject_framework(source, manifest, page_css, page_js)
        atomic_write(output_dir / page["output"], result)

    viewer = index_template.replace("{{PROJECT_NAME}}", html.escape(config["project"]["name"]))
    viewer = viewer.replace("{{PROJECT_SUBTITLE}}", html.escape(config["project"].get("subtitle", "原型演示")))
    viewer = viewer.replace("{{NAV_CONFIG_JSON}}", json.dumps(nav_config(config), ensure_ascii=False, indent=2).replace("<", "\\u003c"))
    viewer = viewer.replace("{{BUILD_ID}}", build_id)
    viewer = viewer.replace("</head>", f"<meta name=\"ds-framework-version\" content=\"{FRAMEWORK_VERSION}\"><meta name=\"ds-framework-fingerprint\" content=\"{fingerprint}\"><meta name=\"ds-build-id\" content=\"{build_id}\">\n</head>", 1)
    atomic_write(output_dir / "index.html", viewer)
    print(f"Built {len(config['pages'])} pages into {output_dir}")
    print(f"Framework {FRAMEWORK_VERSION} / fingerprint {fingerprint}")
    print(f"Build ID {build_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Directory containing prototype.config.json")
    parser.add_argument("--output", type=Path, required=True, help="Standalone prototype output directory")
    args = parser.parse_args()
    try:
        build(args.source.resolve(), args.output.resolve())
    except (OSError, ValueError, TypeError) as error:
        print(f"ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
