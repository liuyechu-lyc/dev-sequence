#!/usr/bin/env python3
"""Shared PRD binding helpers for prototype source and output validation."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")


def markdown_content(text: str) -> str:
    """Ignore code examples when inspecting actual document metadata and IDs."""
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)[0]
            length = len(match.group(1))
            if fence is None:
                fence = (marker, length)
            elif marker == fence[0] and length >= fence[1] and not line[match.end():].strip():
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def prd_version(text: str) -> str | None:
    content = markdown_content(text)
    for key in ("当前版本", "版本"):
        matches = list(re.finditer(rf"^\s*\|\s*{key}\s*\|\s*([^|]+?)\s*\|", content, re.M))
        matches += list(re.finditer(rf"^\s*(?:>\s*)?(?:-\s*)?{key}\s*[:：]\s*([^｜|\n]+)", content, re.M))
        for match in matches:
            value = match.group(1).strip().strip("`*")
            if value and value.casefold() not in {"日期", "日期时间", "时间", "date", "datetime", "内容", "字段"}:
                return value
    return None


def versions_equal(first: str, second: str) -> bool:
    return first.strip().casefold() == second.strip().casefold()


def declared_prd_ids(text: str) -> set[str]:
    """Collect IDs defined by headings, first table cells, or labeled bullet rows."""
    declared = set()
    for line in markdown_content(text).splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s+", line):
            # Only the leading definition is an ID; later IDs may be references.
            match = ID_RE.search(line)
            if match:
                declared.add(match.group())
        elif line.lstrip().startswith("|"):
            cell = line.strip().split("|")[1]
            declared.update(ID_RE.findall(cell))
        else:
            match = re.match(r"^\s*(?:[-*>]\s*)?[`*_]*([A-Z][A-Z0-9]*-\d+)[`*_]*\s*[:：]", line)
            if match:
                declared.add(match.group(1))
    return declared


def prd_binding(source_dir: Path, config: dict) -> tuple[dict, str | None]:
    """Resolve the source PRD and expose an honest build-time verification status."""
    project = config.get("project") if isinstance(config.get("project"), dict) else {}
    prd = project.get("prd") if isinstance(project.get("prd"), dict) else {}
    binding = {
        "prototypeVersion": project.get("version"),
        "prd": {"path": prd.get("path"), "version": prd.get("version"), "status": "unverified"},
    }
    if not isinstance(prd.get("path"), str) or not prd["path"].strip():
        return binding, None
    path = (source_dir / prd["path"]).resolve()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return binding, None
    actual = prd_version(text)
    binding["prd"].update({"actualVersion": actual, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    if actual and isinstance(prd.get("version"), str):
        binding["prd"]["status"] = "verified" if versions_equal(actual, prd["version"]) else "mismatch"
    return binding, text
