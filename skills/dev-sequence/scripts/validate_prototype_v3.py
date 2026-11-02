#!/usr/bin/env python3
"""Validate Dev Sequence v3 source data and generated standalone output."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from prototype_content import declared_prd_ids, prd_binding


CHANGE_TYPES = {"new", "modified", "existing"}
CHANGE_IMPACTS = {"business", "interaction", "visual-only", "none"}
VIEWPORT_TYPES = {"pc", "tablet", "mobile"}
VIEWPORT_LABELS = {"pc": "PC", "tablet": "平板", "mobile": "手机"}
SCROLL_CONSUMER_VALUES = {"x", "y", "both"}
OVERLAY_MODE_VALUES = {"modal", "nonmodal"}
FRAMEWORK_VERSION = "3.14.0"
PROTOCOL_VERSION = 5
SPEC_SCHEMA_VERSION = 5
PAGE_KINDS = {"overview", "business", "component-guide", "diagram-guide"}
GUIDE_KINDS = {"component-guide", "diagram-guide"}
ASCII_FILE = re.compile(r"^[A-Za-z0-9._-]+\.html$")
BUILD_ID_RE = re.compile(r"^[0-9a-f]{12}$")
CONTROL_TYPES = {
    "文本", "单行文本", "多行文本", "单选", "多选", "单选组", "多选组",
    "Tab", "日期", "时间", "日期段", "时间段", "按钮", "链接", "表格",
    "状态", "图片", "图标", "分页",
}
TEXT_INPUT_TYPES = {"单行文本", "多行文本"}
CHOICE_TYPES = {"单选", "多选", "单选组", "多选组"}
DATE_TIME_TYPES = {"日期", "时间", "日期段", "时间段"}
BUTTON_ROLES = {"save-submit", "action"}
PROTOTYPE_CHANGE_ACTIONS = {"新增", "修改", "删除"}
PROTOTYPE_VERSION = re.compile(r"^V(\d+)\.(\d+)$")
FAQ_ROLES = {"研发", "测试"}
FAQ_STATUSES = {"待确认", "已答复", "已关闭"}


def load_json(path: Path, errors: list[str]) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        errors.append(f"{path}: invalid JSON: {error}")
        return {}


def has_current_change(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("changeType") in {"new", "modified"}:
            return True
        return any(has_current_change(item) for item in value.values())
    if isinstance(value, list):
        return any(has_current_change(item) for item in value)
    return False


def validate_change_tree(value: object, label: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        if "changeType" in value and value["changeType"] not in CHANGE_TYPES:
            errors.append(f"{label}: invalid changeType={value['changeType']}")
        if "changeImpact" in value and value["changeImpact"] not in CHANGE_IMPACTS:
            errors.append(f"{label}: invalid changeImpact={value['changeImpact']}")
        for key, child in value.items():
            validate_change_tree(child, f"{label}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_change_tree(child, f"{label}[{index}]", errors)


def page_references(value: object, label: str, errors: list[str]) -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []
    if isinstance(value, dict):
        if "references" in value:
            if not value.get("key") or not value.get("title") or "sections" in value:
                errors.append(f"{label}.references: references are only allowed on spec sections")
            items = value["references"]
            if not isinstance(items, list) or not items:
                errors.append(f"{label}.references: must be a non-empty array")
            else:
                for index, item in enumerate(items):
                    item_label = f"{label}.references[{index}]"
                    if not isinstance(item, dict) or set(item) != {"pageId"}:
                        errors.append(f"{item_label}: must contain only pageId")
                        continue
                    if not isinstance(item.get("pageId"), str) or not item["pageId"]:
                        errors.append(f"{item_label}.pageId: non-empty string is required")
                        continue
                    references.append((item["pageId"], item_label))
        for key, child in value.items():
            if key != "references":
                references.extend(page_references(child, f"{label}.{key}", errors))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            references.extend(page_references(child, f"{label}[{index}]", errors))
    return references


def validate_viewports(page: dict, label: str, errors: list[str]) -> None:
    viewports = page.get("viewports")
    if not isinstance(viewports, dict):
        errors.append(f"{label}: viewports is required")
        return
    supported = viewports.get("supported")
    if not isinstance(supported, list) or not supported:
        errors.append(f"{label}: viewports.supported must be a non-empty array")
        return
    types = []
    for viewport in supported:
        if not isinstance(viewport, dict) or viewport.get("type") not in VIEWPORT_TYPES:
            errors.append(f"{label}: invalid viewport declaration")
            continue
        types.append(viewport["type"])
        if not isinstance(viewport.get("width"), (int, float)) or viewport["width"] <= 0:
            errors.append(f"{label}: viewport width must be positive")
        if not isinstance(viewport.get("height"), (int, float)) or viewport["height"] <= 0:
            errors.append(f"{label}: viewport height must be positive")
    if len(types) != len(set(types)):
        errors.append(f"{label}: duplicate viewport type")
    if viewports.get("default") not in types:
        errors.append(f"{label}: default viewport must exist in supported")


def anchor_count(source: str, key: str) -> int:
    escaped = re.escape(key)
    patterns = (
        rf'data-ds-spec-anchor=["\']{escaped}["\']',
        rf'["\']data-ds-spec-anchor["\']\s*:\s*["\']{escaped}["\']',
        rf'(?<![\w-])anchor=["\']{escaped}["\']',
        rf'(?<![\w-])anchor\s*:\s*["\']{escaped}["\']',
    )
    return sum(len(re.findall(pattern, source)) for pattern in patterns)


def validate_scroll_consumers(source: str, label: str, errors: list[str]) -> None:
    declarations = re.findall(r'data-ds-scroll-consumer=["\']([^"\']+)["\']', source)
    declarations.extend(re.findall(r'["\']data-ds-scroll-consumer["\']\s*:\s*["\']([^"\']+)["\']', source))
    for declaration in declarations:
        if declaration not in SCROLL_CONSUMER_VALUES:
            errors.append(
                f"{label}: data-ds-scroll-consumer must be x, y or both; got {declaration}"
            )


def validate_overlay_modes(source: str, label: str, errors: list[str]) -> None:
    declarations = re.findall(r'data-ds-overlay-mode=["\']([^"\']+)["\']', source)
    declarations.extend(re.findall(r'["\']data-ds-overlay-mode["\']\s*:\s*["\']([^"\']+)["\']', source))
    for declaration in declarations:
        if declaration not in OVERLAY_MODE_VALUES:
            errors.append(
                f"{label}: data-ds-overlay-mode must be modal or nonmodal; got {declaration}"
            )


def validate_overview(config: dict, errors: list[str]) -> None:
    overview = config.get("overview")
    label = "prototype.config.json.overview"
    if not isinstance(overview, dict):
        errors.append(f"{label}: overview object is required")
        return
    if not isinstance(overview.get("summary"), str) or not overview["summary"]:
        errors.append(f"{label}.summary: non-empty string is required")
    goals = overview.get("goals")
    if not isinstance(goals, list) or not goals or any(not isinstance(item, str) or not item for item in goals):
        errors.append(f"{label}.goals: non-empty string array is required")
    rules = overview.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append(f"{label}.rules: non-empty array is required")
    else:
        for index, item in enumerate(rules):
            if not isinstance(item, dict) or any(not isinstance(item.get(field), str) or not item[field] for field in ("title", "content")):
                errors.append(f"{label}.rules[{index}]: title and content are required")

    glossary = overview.get("glossary")
    if not isinstance(glossary, list):
        errors.append(f"{label}.glossary: array is required")
    else:
        terms: list[str] = []
        for index, item in enumerate(glossary):
            if not isinstance(item, dict) or any(not isinstance(item.get(field), str) or not item[field] for field in ("term", "definition")):
                errors.append(f"{label}.glossary[{index}]: term and definition are required")
                continue
            terms.append(item["term"])
        if len(terms) != len(set(terms)):
            errors.append(f"{label}.glossary: terms must be unique")

    change_log_order = overview.get("changeLogOrder")
    if change_log_order != "newest-first":
        errors.append(f"{label}.changeLogOrder: must be newest-first")

    change_log = overview.get("prototypeChangeLog")
    if not isinstance(change_log, list):
        errors.append(f"{label}.prototypeChangeLog: array is required")
    else:
        ordered_versions: list[str] = []
        version_datetimes: dict[str, set[str]] = {}
        for index, item in enumerate(change_log):
            item_label = f"{label}.prototypeChangeLog[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{item_label}: object is required")
                continue
            version = item.get("version")
            if not isinstance(version, str) or not PROTOTYPE_VERSION.fullmatch(version):
                errors.append(f"{item_label}.version: use V{{major}}.{{minor}}, starting from V1.0")
            else:
                if version not in ordered_versions:
                    ordered_versions.append(version)
                version_datetimes.setdefault(version, set())
            if not isinstance(item.get("datetime"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", item["datetime"]):
                errors.append(f"{item_label}.datetime: use YYYY-MM-DD HH:mm")
            elif isinstance(version, str) and PROTOTYPE_VERSION.fullmatch(version):
                version_datetimes[version].add(item["datetime"])
            if not isinstance(item.get("terminal"), str) or not item["terminal"]:
                errors.append(f"{item_label}.terminal: non-empty string is required")
            if not isinstance(item.get("summary"), str) or not item["summary"]:
                errors.append(f"{item_label}.summary: non-empty string is required")
            for field in ("pages", "modules"):
                refs = item.get(field)
                if not isinstance(refs, list) or not refs:
                    errors.append(f"{item_label}.{field}: non-empty array is required")
                    continue
                if len(refs) != 1:
                    errors.append(f"{item_label}.{field}: exactly one reference is required per change-log row")
                for ref_index, ref in enumerate(refs):
                    ref_label = f"{item_label}.{field}[{ref_index}]"
                    if not isinstance(ref, dict) or not isinstance(ref.get("name"), str) or not ref["name"]:
                        errors.append(f"{ref_label}: name is required")
                    elif ref.get("action") not in PROTOTYPE_CHANGE_ACTIONS:
                        errors.append(f"{ref_label}: action must be 新增, 修改 or 删除")
        if ordered_versions:
            if ordered_versions[-1] != "V1.0":
                errors.append(f"{label}.prototypeChangeLog: the oldest version batch must be V1.0")
            parsed_versions = [
                tuple(int(part) for part in PROTOTYPE_VERSION.fullmatch(version).groups())
                for version in ordered_versions
            ]
            if any(current >= previous for previous, current in zip(parsed_versions, parsed_versions[1:])):
                errors.append(f"{label}.prototypeChangeLog: version batches must decrease in source order")
        for version, datetimes in version_datetimes.items():
            if len(datetimes) != 1:
                errors.append(f"{label}.prototypeChangeLog: {version} must use one shared datetime")
        for name, key_for in (
            ("version", lambda item: item.get("version")),
            ("datetime", lambda item: (item.get("version"), item.get("datetime"))),
            ("terminal", lambda item: (item.get("version"), item.get("datetime"), item.get("terminal"))),
        ):
            closed: set[object] = set()
            current = object()
            for index, item in enumerate(change_log):
                if not isinstance(item, dict):
                    continue
                key = repr(key_for(item))
                if key == current:
                    continue
                if key in closed:
                    errors.append(
                        f"{label}.prototypeChangeLog[{index}].{name}: identical batch values must be consecutive for merged rows"
                    )
                    break
                closed.add(key)
                current = key

    faq = overview.get("faq")
    if not isinstance(faq, list):
        errors.append(f"{label}.faq: array is required")
    else:
        faq_ids: list[str] = []
        for index, item in enumerate(faq):
            item_label = f"{label}.faq[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{item_label}: object is required")
                continue
            for field in ("id", "raisedAt", "question"):
                if not isinstance(item.get(field), str) or not item[field]:
                    errors.append(f"{item_label}.{field}: non-empty string is required")
            if isinstance(item.get("id"), str):
                faq_ids.append(item["id"])
            if item.get("role") not in FAQ_ROLES:
                errors.append(f"{item_label}.role: must be 研发 or 测试")
            if item.get("status") not in FAQ_STATUSES:
                errors.append(f"{item_label}.status: must be 待确认, 已答复 or 已关闭")
            for optional_field in ("scope", "answer"):
                if optional_field in item and not isinstance(item[optional_field], str):
                    errors.append(f"{item_label}.{optional_field}: must be a string")
        if len(faq_ids) != len(set(faq_ids)):
            errors.append(f"{label}.faq: ids must be unique")

    tracking = overview.get("tracking")
    if not isinstance(tracking, dict) or tracking.get("mode") not in {"none", "url"}:
        errors.append(f"{label}.tracking: mode must be none or url")
    elif tracking["mode"] == "url" and (not isinstance(tracking.get("url"), str) or not tracking["url"]):
        errors.append(f"{label}.tracking.url: non-empty URL is required when mode=url")


def validate_specs(specs: dict, source_text: str, label: str, errors: list[str], warnings: list[str], allow_extra_anchors: bool = False, require_lifecycle: bool = False) -> None:
    validate_change_tree(specs, label, errors)
    if specs.get("enabled") is False:
        return
    page_spec = specs.get("page")
    modules = specs.get("modules")
    if not isinstance(page_spec, dict) or not isinstance(page_spec.get("sections"), list):
        errors.append(f"{label}: page.sections is required when specs are enabled")
    elif any(section.get("key") == "supported-viewports" for section in page_spec["sections"] if isinstance(section, dict)):
        errors.append(f"{label}: supported-viewports is generated from prototype.config.json and must not be maintained in specs")
    if not isinstance(modules, list):
        errors.append(f"{label}: modules must be an array")
        return
    keys: list[str] = []
    for index, module in enumerate(modules):
        path = f"{label}.modules[{index}]"
        if not isinstance(module, dict):
            errors.append(f"{path}: module must be an object")
            continue
        key = module.get("key")
        if not isinstance(key, str) or not key:
            errors.append(f"{path}: key is required")
            continue
        keys.append(key)
        if "target" in module:
            errors.append(f"{path}: target is forbidden; use data-ds-spec-anchor={key}")
        if module.get("layer", "base") not in {"base", "modal"}:
            errors.append(f"{path}: layer must be base or modal")
        if module.get("layer") == "modal" and "data-ds-overlay-root" not in source_text:
            errors.append(f"{path}: modal modules require a data-ds-overlay-root declaration")
        sections = module.get("sections")
        if not isinstance(sections, list):
            errors.append(f"{path}: sections must be an array")
            sections = []
        control_sections = [
            section for section in sections
            if isinstance(section, dict) and section.get("type") == "controls"
        ]
        if len(control_sections) != 1:
            errors.append(f"{path}: exactly one type=controls section is required")
        elif not isinstance(control_sections[0].get("items"), list) or not control_sections[0]["items"]:
            errors.append(f"{path}: controls section must contain at least one item")
        else:
            for control_index, control in enumerate(control_sections[0]["items"]):
                control_path = f"{path}.controls[{control_index}]"
                if not isinstance(control, dict):
                    errors.append(f"{control_path}: control item must be an object")
                    continue
                control_type = control.get("controlType")
                for field in ("name", "controlType", "dataSource"):
                    if not isinstance(control.get(field), str) or not control[field].strip():
                        errors.append(f"{control_path}: {field} is required")
                if control_type not in CONTROL_TYPES:
                    errors.append(f"{control_path}: unsupported controlType={control_type}")
                if control_type in TEXT_INPUT_TYPES:
                    if "defaultValue" not in control:
                        errors.append(f"{control_path}: {control_type} requires defaultValue")
                    if not isinstance(control.get("required"), bool):
                        errors.append(f"{control_path}: {control_type} requires boolean required")
                    if not isinstance(control.get("constraints"), str) or not control["constraints"].strip():
                        errors.append(f"{control_path}: {control_type} requires constraints")
                if control_type in CHOICE_TYPES:
                    if "defaultValue" not in control:
                        errors.append(f"{control_path}: {control_type} requires defaultValue")
                    if not isinstance(control.get("required"), bool):
                        errors.append(f"{control_path}: {control_type} requires boolean required")
                    if not isinstance(control.get("options"), str) or not control["options"].strip():
                        errors.append(f"{control_path}: {control_type} requires options")
                if control_type == "Tab" and "defaultValue" not in control:
                    errors.append(f"{control_path}: Tab requires defaultValue")
                if control_type in DATE_TIME_TYPES:
                    if "defaultValue" not in control:
                        errors.append(f"{control_path}: {control_type} requires defaultValue")
                    if not isinstance(control.get("selectableRange"), str) or not control["selectableRange"].strip():
                        errors.append(f"{control_path}: {control_type} requires selectableRange")
                if control_type == "按钮":
                    button_role = control.get("buttonRole")
                    if button_role not in BUTTON_ROLES:
                        errors.append(f"{control_path}: 按钮 requires buttonRole=save-submit or action")
                    if button_role == "save-submit":
                        for field in ("validationRules", "successResult", "failureResult"):
                            if not isinstance(control.get(field), str) or not control[field].strip():
                                errors.append(f"{control_path}: save-submit button requires {field}")
                        if not isinstance(control.get("note"), str) or not control["note"].strip():
                            message = f"{control_path}: describe submission lifecycle in note (pending, request failure, timeout, recovery, duplicates or explicit non-applicability)"
                            (errors if require_lifecycle else warnings).append(message)
                    if button_role == "action":
                        if not isinstance(control.get("actionResult"), str) or not control["actionResult"].strip():
                            errors.append(f"{control_path}: action button requires actionResult")
        impact = module.get("changeImpact", "none")
        if impact in {"business", "interaction"} and not has_current_change(module):
            errors.append(f"{path}: {impact} change requires a new/modified spec item")
        count = anchor_count(source_text, key)
        if count == 0:
            errors.append(f"{path}: missing stable anchor data-ds-spec-anchor={key}")
        elif count > 1:
            warnings.append(f"{path}: anchor appears {count} times in source; verify only one is rendered at a time")
    if len(keys) != len(set(keys)):
        errors.append(f"{label}: duplicate module key")
    declared = set(keys)
    anchors = set(re.findall(r'data-ds-spec-anchor=["\']([^"\']+)', source_text))
    anchors.update(re.findall(r'["\']data-ds-spec-anchor["\']\s*:\s*["\']([^"\']+)', source_text))
    anchors.update(re.findall(r'(?<![\w-])anchor=["\']([^"\']+)', source_text))
    anchors.update(re.findall(r'(?<![\w-])anchor\s*:\s*["\']([^"\']+)', source_text))
    if not allow_extra_anchors:
        for orphan in sorted(anchors - declared):
            errors.append(f"{label}: orphan DOM anchor without module spec: {orphan}")


def validate_content_contract(config: dict, source_dir: Path, errors: list[str], warnings: list[str], strict: bool = False) -> dict:
    """Check business bindings and reference integrity without claiming UI correctness."""
    declared_standard = config.get("contentStandardVersion")
    if declared_standard is not None and (type(declared_standard) is not int or declared_standard != 1):
        errors.append("prototype.config.json: contentStandardVersion must be 1 when declared")
    strict = strict or declared_standard == 1
    if not strict:
        warnings.append("Legacy content contract: PRD binding, traceability and demo completeness are not guaranteed; migrate to contentStandardVersion=1. This is not a complete requirements review.")
    missing = errors if strict else warnings
    project = config.get("project") if isinstance(config.get("project"), dict) else {}
    for field in ("version",):
        if not isinstance(project.get(field), str) or not project[field].strip():
            missing.append(f"project.{field}: prototype business version is required by content standard 1")
    prd = project.get("prd")
    if not isinstance(prd, dict):
        missing.append("project.prd: path and version are required; PRD coverage is unverified")
        prd = {}
    for field in ("path", "version"):
        if not isinstance(prd.get(field), str) or not prd[field].strip():
            missing.append(f"project.prd.{field}: non-empty string is required; PRD coverage is unverified")
    if isinstance(prd.get("path"), str) and Path(prd["path"]).is_absolute():
        errors.append("project.prd.path: use a path relative to the app directory")
    binding, prd_text = prd_binding(source_dir, config)
    prd_ids = None
    if prd.get("path"):
        if prd_text is None:
            missing.append("project.prd.path: PRD cannot be read; version and ID references were not checked")
        else:
            prd_ids = declared_prd_ids(prd_text)
            if binding["prd"]["status"] == "mismatch":
                errors.append(f"project.prd.version: declared {prd.get('version')} does not match PRD current version {binding['prd'].get('actualVersion')}")
            elif binding["prd"]["status"] != "verified":
                missing.append("project.prd: current version could not be verified; add explicit PRD metadata 当前版本")
            if not prd_ids:
                missing.append("project.prd: no declared requirement/acceptance IDs were found; reference coverage was not checked")

    pages = {page["id"]: page for page in config.get("pages", []) if isinstance(page, dict) and isinstance(page.get("id"), str)}
    trace = config.get("traceability")
    if "traceability" in config and not isinstance(trace, list):
        errors.append("traceability: array is required when declared")
    if not isinstance(trace, list) or not trace:
        missing.append("traceability: non-empty mapping array is required; requirements coverage was not checked")
        trace = []
    for index, row in enumerate(trace):
        label = f"traceability[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{label}: object is required")
            continue
        for field in ("requirementId", "scenario"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append(f"{label}.{field}: non-empty string is required")
        for field in ("moduleKey", "prdPageId", "notes", "reason", "evidence"):
            if field in row and not isinstance(row[field], str) and not (field in {"moduleKey", "prdPageId"} and row[field] is None):
                errors.append(f"{label}.{field}: string is required when declared")
        if not isinstance(row.get("coverage"), str) or row["coverage"] not in {"covered", "partial", "pending", "not-applicable"}:
            errors.append(f"{label}.coverage: must be covered, partial, pending or not-applicable")
        elif row["coverage"] != "covered":
            warnings.append(f"{label}: design coverage is {row['coverage']}; no implementation or acceptance pass is implied")
        for field, nonempty in (("ruleIds", False), ("acceptanceIds", True)):
            values = row.get(field, [] if not nonempty else None)
            if not isinstance(values, list) or (nonempty and not values) or any(not isinstance(value, str) or not value for value in values):
                errors.append(f"{label}.{field}: {'non-empty ' if nonempty else ''}string array is required")
                continue
            if len(values) != len(set(values)):
                errors.append(f"{label}.{field}: duplicate ID")
        reference_ids = [row.get("requirementId"), row.get("prdPageId")]
        for field in ("ruleIds", "acceptanceIds"):
            if isinstance(row.get(field), list):
                reference_ids.extend(row[field])
        if prd_ids is not None:
            for reference in reference_ids:
                if isinstance(reference, str) and reference not in prd_ids:
                    errors.append(f"{label}: referenced ID {reference} is not declared in the bound PRD")
        page_id = row.get("pageId")
        if page_id is None:
            for field in ("reason", "evidence"):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    errors.append(f"{label}.{field}: no-UI mapping requires an explanation and other verification reference")
            if row.get("moduleKey"):
                errors.append(f"{label}.moduleKey: no-UI mappings cannot reference a UI module")
        elif not isinstance(page_id, str) or page_id not in pages:
            errors.append(f"{label}.pageId: unknown registered page {page_id}")
        elif isinstance(row.get("moduleKey"), str) and row["moduleKey"]:
            page = pages[page_id]
            spec_path = source_dir / str(page.get("specs", ""))
            specs = load_json(spec_path, errors) if page.get("specs") and spec_path.is_file() else {}
            keys = {module.get("key") for module in specs.get("modules", []) if isinstance(module, dict)}
            if row["moduleKey"] not in keys:
                errors.append(f"{label}.moduleKey: {row['moduleKey']} is not a spec module of {page_id}")
    demo = config.get("overview", {}).get("demo") if isinstance(config.get("overview"), dict) else None
    if not isinstance(demo, dict):
        if isinstance(config.get("overview"), dict) and "demo" in config["overview"]:
            errors.append("overview.demo: object is required when declared")
        missing.append("overview.demo: simulation scope, paths, failure triggers, reset and persistence must be declared")
    else:
        for field in ("scope", "reset", "persistence"):
            if not isinstance(demo.get(field), str) or not demo[field].strip():
                errors.append(f"overview.demo.{field}: non-empty string is required")
        paths = demo.get("paths")
        if not isinstance(paths, list) or not paths:
            errors.append("overview.demo.paths: non-empty path array is required")
        else:
            for index, path in enumerate(paths):
                label = f"overview.demo.paths[{index}]"
                if not isinstance(path, dict):
                    errors.append(f"{label}: object is required")
                    continue
                if not isinstance(path.get("name"), str) or not path["name"].strip():
                    errors.append(f"{label}.name: non-empty string is required")
                for field in ("steps", "pageIds"):
                    values = path.get(field)
                    if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
                        errors.append(f"{label}.{field}: non-empty string array is required")
                    elif field == "pageIds":
                        for page_id in values:
                            if page_id not in pages:
                                errors.append(f"{label}.pageIds: unknown registered page {page_id}")
        failures = demo.get("failureTriggers")
        if not isinstance(failures, list) or any(not isinstance(value, str) or not value for value in failures):
            errors.append("overview.demo.failureTriggers: string array is required")
        elif not failures and (not isinstance(demo.get("failureNotApplicableReason"), str) or not demo["failureNotApplicableReason"].strip()):
            errors.append("overview.demo: empty failureTriggers requires failureNotApplicableReason")
    return binding


def extract_manifest(page_html: str) -> dict | None:
    match = re.search(r'<script id="prototype-manifest" type="application/json">(.*?)</script>', page_html, re.S)
    if not match:
        return None
    return json.loads(match.group(1))


def validate(source_dir: Path, output_dir: Path | None, strict_content: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    config_path = source_dir / "prototype.config.json"
    config = load_json(config_path, errors)
    if not config:
        return errors, warnings
    if config.get("schemaVersion") != 3:
        errors.append("prototype.config.json: schemaVersion must be 3")
    if not isinstance(config.get("project"), dict) or not config["project"].get("name"):
        errors.append("prototype.config.json: project.name is required")
    validate_overview(config, errors)
    groups = config.get("navigation")
    pages = config.get("pages")
    if not isinstance(groups, list) or not isinstance(pages, list) or not pages:
        errors.append("prototype.config.json: navigation and non-empty pages are required")
        return errors, warnings
    binding = validate_content_contract(config, source_dir, errors, warnings, strict=strict_content)
    group_ids = [group.get("id") for group in groups if isinstance(group, dict)]
    if len(group_ids) != len(set(group_ids)) or any(not item for item in group_ids):
        errors.append("prototype.config.json: navigation ids must be unique and non-empty")
    page_ids: list[str] = []
    outputs: list[str] = []
    fingerprints: set[str] = set()
    build_ids: set[str] = set()
    page_registry = {
        page.get("id"): page
        for page in pages
        if isinstance(page, dict) and isinstance(page.get("id"), str) and page.get("id")
    }
    for guide_kind in GUIDE_KINDS:
        guide_group_ids = {
            page.get("navGroup")
            for page in pages
            if isinstance(page, dict) and page.get("kind") == guide_kind
        }
        for group_id in guide_group_ids:
            mixed = [
                page.get("id")
                for page in pages
                if isinstance(page, dict)
                and page.get("navGroup") == group_id
                and page.get("kind", "business") != guide_kind
            ]
            if mixed:
                errors.append(
                    f"prototype.config.json: {guide_kind} navGroup={group_id} "
                    f"also contains pages of another kind {mixed}"
                )
    for index, page in enumerate(pages):
        label = f"pages[{index}]"
        if not isinstance(page, dict):
            errors.append(f"{label}: page must be an object")
            continue
        page_id = page.get("id")
        output = page.get("output")
        page_ids.append(page_id)
        outputs.append(output)
        for field in ("id", "title", "output", "navGroup", "businessEnd", "description"):
            if not isinstance(page.get(field), str) or not page[field]:
                errors.append(f"{label}: {field} is required")
        if page.get("navGroup") not in group_ids:
            errors.append(f"{label}: unknown navGroup={page.get('navGroup')}")
        if not isinstance(output, str) or not ASCII_FILE.fullmatch(output):
            errors.append(f"{label}: output must be an ASCII .html filename")
        if page.get("changeType", "existing") not in CHANGE_TYPES:
            errors.append(f"{label}: invalid changeType")
        if page.get("changeImpact", "none") not in CHANGE_IMPACTS:
            errors.append(f"{label}: invalid changeImpact")
        page_kind = page.get("kind", "business")
        if page_kind not in PAGE_KINDS:
            errors.append(f"{label}: invalid kind={page_kind}")
        changes = page.get("versionChanges", [])
        if page.get("changeType") in {"new", "modified"} and not changes:
            errors.append(f"{label}: changed page requires versionChanges")
        validate_viewports(page, label, errors)
        if page.get("kind") == "overview":
            source_text = ""
        else:
            source_path = source_dir / str(page.get("source", ""))
            if not source_path.is_file():
                errors.append(f"{label}: missing business source {source_path}")
                source_text = ""
            else:
                source_text = source_path.read_text(encoding="utf-8")
        specs_path = source_dir / str(page.get("specs", "")) if page.get("specs") else None
        specs = load_json(specs_path, errors) if specs_path else {"enabled": False}
        if page_kind in GUIDE_KINDS and specs.get("enabled") is not False:
            errors.append(f"{label}: {page_kind} pages must disable technical specs")
        for target_id, reference_label in page_references(specs, f"{label}.specs", errors):
            target = page_registry.get(target_id)
            if not target:
                errors.append(f"{reference_label}: unknown pageId={target_id}")
            elif target_id == page_id:
                errors.append(f"{reference_label}: page cannot reference itself")
            elif target.get("kind") != "component-guide":
                errors.append(f"{reference_label}: target page must use kind=component-guide")
        validate_specs(
            specs,
            source_text,
            f"{label}.specs",
            errors,
            warnings,
            allow_extra_anchors=config.get("sourceMode") == "shared-spa-bundle",
            require_lifecycle=strict_content or config.get("contentStandardVersion") == 1,
        )
        validate_scroll_consumers(source_text, label, errors)
        validate_overlay_modes(source_text, label, errors)

        if output_dir and isinstance(output, str):
            generated = output_dir / output
            if not generated.is_file():
                errors.append(f"{label}: missing generated output {generated}")
                continue
            generated_text = generated.read_text(encoding="utf-8")
            if "<!-- DS-FRAMEWORK-START -->" not in generated_text:
                errors.append(f"{label}: generated page lacks managed framework block")
            for cache_token in (
                'http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"',
                'http-equiv="Pragma" content="no-cache"',
                'http-equiv="Expires" content="0"',
            ):
                if cache_token not in generated_text:
                    errors.append(f"{label}: generated page lacks cache-control token {cache_token}")
            if page.get("kind") == "overview":
                for overview_token in (
                    'data-overview-summary',
                    'data-overview-goals',
                    'data-overview-glossary',
                    'data-overview-rules',
                    'data-overview-pages',
                    'data-overview-change-log',
                    'data-overview-faq',
                    'data-overview-tracking',
                    'data-overview-binding',
                    'data-overview-demo',
                    'data-overview-traceability',
                ):
                    if overview_token not in generated_text:
                        errors.append(f"{label}: generated overview lacks {overview_token}")
                for glossary_item in config["overview"].get("glossary", []):
                    if glossary_item["term"] not in generated_text:
                        errors.append(f"{label}: generated overview lacks glossary term {glossary_item['term']}")
            if "spec-markers-layout" in generated_text:
                errors.append(f"{label}: generated page still contains legacy marker layout reporting")
            try:
                manifest = extract_manifest(generated_text)
            except Exception as error:
                errors.append(f"{label}: invalid generated manifest: {error}")
                manifest = None
            if not manifest:
                errors.append(f"{label}: missing generated manifest")
            else:
                if manifest.get("pageId") != page_id:
                    errors.append(f"{label}: generated pageId mismatch")
                if manifest.get("businessBinding") != binding:
                    errors.append(f"{label}: generated businessBinding does not match the current PRD/version; rebuild is required")
                if (
                    manifest.get("protocolVersion") != PROTOCOL_VERSION
                    or manifest.get("frameworkVersion") != FRAMEWORK_VERSION
                    or manifest.get("specSchemaVersion") != SPEC_SCHEMA_VERSION
                ):
                    errors.append(f"{label}: generated version metadata mismatch")
                build_id = manifest.get("buildId")
                if not isinstance(build_id, str) or not BUILD_ID_RE.fullmatch(build_id):
                    errors.append(f"{label}: generated manifest has invalid buildId")
                else:
                    build_ids.add(build_id)
                for runtime_token in (
                    "--ds-marker-edge-inset: 2px",
                    "box-sizing: border-box",
                    "function clampMarkerCoordinate",
                    "maximumLeft = viewportLeft + viewportWidth - markerSize - markerEdgeInset",
                    "data-ds-scroll-consumer",
                    "function handleTrackpadPan",
                    "function exclusiveScrollConsumerFor",
                    "function hasScrollableOverflow",
                    "canvas-pan",
                    "overscroll-behavior-x: none",
                    "overscroll-behavior: none",
                ):
                    if runtime_token not in generated_text:
                        errors.append(f"{label}: generated page lacks framework runtime token {runtime_token}")
                if specs.get("enabled") is not False:
                    generated_sections = manifest.get("specs", {}).get("page", {}).get("sections", [])
                    compatibility = next((item for item in generated_sections if item.get("key") == "supported-viewports"), None)
                    expected_labels = [VIEWPORT_LABELS[item["type"]] for item in page["viewports"]["supported"]]
                    if not compatibility or not compatibility.get("generated"):
                        errors.append(f"{label}: generated page specs lack supported-viewports")
                    elif any(item not in compatibility.get("content", "") for item in expected_labels):
                        errors.append(f"{label}: supported-viewports does not match page viewport declaration")
                fingerprints.add(str(manifest.get("frameworkFingerprint")))

    if len(page_ids) != len(set(page_ids)):
        errors.append("prototype.config.json: duplicate page id")
    if len(outputs) != len(set(outputs)):
        errors.append("prototype.config.json: duplicate output filename")
    if sum(1 for page in pages if page.get("kind") == "overview") != 1:
        errors.append("prototype.config.json: exactly one overview page is required")
    if output_dir:
        from build_prototype_v3 import framework_assets, prototype_build_id
        try:
            expected_build_id = prototype_build_id(source_dir, config, *framework_assets())
        except (OSError, ValueError, TypeError) as error:
            expected_build_id = None
            errors.append(f"generated output: current build inputs could not be checked: {error}")
        if expected_build_id and build_ids and build_ids != {expected_build_id}:
            errors.append("generated output: buildId does not match current source/configuration/PRD; rebuild is required")
        index_path = output_dir / "index.html"
        if not index_path.is_file():
            errors.append("generated output: index.html is missing")
        else:
            index_text = index_path.read_text(encoding="utf-8")
            for token in (
                f"var PROTOCOL_VERSION = {PROTOCOL_VERSION}",
                "var BUILD_ID = '",
                "function versionedPageUrl(file)",
                "url.searchParams.set('v', BUILD_ID)",
                "protoFrame.src = versionedPageUrl(page.file)",
                'http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"',
                'http-equiv="Pragma" content="no-cache"',
                'http-equiv="Expires" content="0"',
                "space-pan-start",
                "space-pan-end",
                "space-pan-reset",
                "canvas-pan",
                "function queueCanvasPan",
                "overscroll-behavior-x: none",
                "border: 0",
                "box-shadow: 0 0 0 2px #bbb",
                "按住空格拖拽页面",
                "松开空格操作原型",
                'id="panHintLead"',
                'id="panHintAction"',
                'class="space-key"',
                'class="pan-hint-slot"',
                "data-page-reference",
                "function renderPageReferences",
                "var pageById = {}",
            ):
                if token not in index_text:
                    errors.append(f"generated output: index.html lacks interaction token {token}")
            index_build_match = re.search(r"var BUILD_ID = '([0-9a-f]{12})'", index_text)
            meta_build_match = re.search(r'<meta name="ds-build-id" content="([0-9a-f]{12})">', index_text)
            if not index_build_match:
                errors.append("generated output: index.html has invalid BUILD_ID")
            if not meta_build_match:
                errors.append("generated output: index.html lacks valid ds-build-id metadata")
            if index_build_match and meta_build_match and index_build_match.group(1) != meta_build_match.group(1):
                errors.append("generated output: index BUILD_ID and ds-build-id metadata mismatch")
            if index_build_match and build_ids and build_ids != {index_build_match.group(1)}:
                errors.append("generated output: page manifests do not share the index BUILD_ID")
            if "href=\"#page=' + encodeURIComponent(page.file)" not in index_text:
                errors.append("generated output: navigation must keep stable unversioned page hashes")
            if 'id="btnDrag"' in index_text:
                errors.append("generated output: persistent drag toggle is forbidden in framework v3.3")
            if "border: 2px solid #bbb" in index_text:
                errors.append("generated output: iframe entity border creates a wheel-event dead zone")
            for forbidden in ('marker-proxy-layer', 'marker-click-proxy', 'spec-markers-layout'):
                if forbidden in index_text:
                    errors.append(f"generated output: legacy marker proxy token is forbidden: {forbidden}")
        if len(fingerprints) > 1:
            errors.append("generated output: mixed framework fingerprints")
        if len(build_ids) > 1:
            errors.append("generated output: mixed project build ids")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict-content", action="store_true", help="Require content standard 1 even for legacy configurations")
    args = parser.parse_args()
    errors, warnings = validate(args.source.resolve(), args.output.resolve() if args.output else None, args.strict_content)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"Validation failed: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"Validation passed: {len(warnings)} warning(s). Structure only; business behavior and browser acceptance still require verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
