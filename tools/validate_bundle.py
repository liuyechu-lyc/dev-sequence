#!/usr/bin/env python3
"""Check owned entry points, package links, portable paths and syntax offline."""
import ast
import json
import re
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent


def validate():
    errors = []
    entries = sorted((BUNDLE / "skills").glob("*/SKILL.md"))
    expected = {"dev-sequence", "dev-sequence-requirements", "dev-sequence-ui", "dev-sequence-prototype", "dev-sequence-tech", "dev-sequence-code", "dev-sequence-test"}
    manifest_path = BUNDLE / "package-manifest.json"
    if manifest_path.exists():
        expected = set(json.loads(manifest_path.read_text(encoding="utf-8")).get("skills", expected))
    if {p.parent.name for p in entries} != expected:
        errors.append("当前包声明的入口不完整")
    for path in BUNDLE.rglob("*"):
        if set(path.relative_to(BUNDLE).parts) & {".git", "__pycache__", ".venv", ".pytest_cache", "dist"}:
            continue
        if path.is_symlink():
            errors.append(f"不允许链接: {path}")
        if not path.is_file():
            continue
        if path.suffix not in {".md", ".py", ".html", ".css", ".js", ".json", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8")
        # Build the retired identifier without embedding a forbidden runtime dependency literal.
        retired = "product" + "-delivery"
        if retired in text or ("/" + "Users/") in text or ("/" + "home/") in text:
            errors.append(f"旧入口或机器绝对路径: {path.relative_to(BUNDLE)}")
        if path.suffix == ".py":
            try: ast.parse(text)
            except SyntaxError as exc: errors.append(f"Python语法错误 {path}: {exc}")
        if path.suffix == ".json":
            try: json.loads(text)
            except ValueError as exc: errors.append(f"JSON错误 {path}: {exc}")
        if path.name == "SKILL.md":
            if not text.startswith("---\n"):
                errors.append(f"缺frontmatter {path}")
            front = text.split("---", 2)[1]
            if f"name: {path.parent.name}\n" not in front or "description:" not in front:
                errors.append(f"入口元信息不一致 {path}")
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#") or "{" in target:
                    continue
                target = target.split("#", 1)[0]
                if target and not (path.parent / target).exists():
                    errors.append(f"失效文档链接 {path.relative_to(BUNDLE)}: {target}")
    return errors


if __name__ == "__main__":
    errors = validate()
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(errors))
