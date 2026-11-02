#!/usr/bin/env python3
"""Build checksummed, dependency-complete full and per-stage zip archives."""
import argparse
import ast
import hashlib
import json
import zipfile
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent
NAMES = {"prd": "requirements", "ui": "ui", "proto": "prototype", "tech": "tech", "code": "code", "test": "test"}
EXCLUDED_PARTS = {".git", "__pycache__", ".DS_Store", ".venv", ".pytest_cache", "dist"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=BUNDLE.parent / "dev-sequence-dist")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    version = next(ast.literal_eval(n.value) for n in ast.parse((BUNDLE / "skills/dev-sequence/scripts/ds.py").read_text(encoding="utf-8")).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in n.targets))
    files = sorted(p for p in BUNDLE.rglob("*") if p.is_file() and not (set(p.relative_to(BUNDLE).parts) & EXCLUDED_PARTS) and p.name != "package-manifest.json")
    manifest = {"name": "dev-sequence", "version": version, "protocolVersion": 1, "python": ">=3.10", "runtimeDependencies": ["Python standard library"], "skills": ["dev-sequence"] + ["dev-sequence-" + n for n in NAMES.values()], "files": {p.relative_to(BUNDLE).as_posix(): sha(p) for p in files}}
    (BUNDLE / "package-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for variant in [None] + list(NAMES):
        selected = [p for p in files if variant is None or not p.relative_to(BUNDLE).as_posix().startswith("skills/") or p.relative_to(BUNDLE).parts[1] in {"dev-sequence", "dev-sequence-" + NAMES[variant]}]
        # Per-stage packages keep usage docs but omit full-suite authoring and tests.
        if variant:
            selected = [p for p in selected if not p.relative_to(BUNDLE).as_posix().startswith("tests/") and p.relative_to(BUNDLE).as_posix() != "tools/package.py"]
        submanifest = dict(manifest)
        submanifest["skills"] = manifest["skills"] if variant is None else ["dev-sequence", "dev-sequence-" + NAMES[variant]]
        submanifest["files"] = {p.relative_to(BUNDLE).as_posix(): sha(p) for p in selected}
        submanifest["selectedStages"] = list(NAMES) if variant is None else [variant]
        name = "dev-sequence-" + version + ("-" + variant if variant else "")
        target = args.output / (name + ".zip")
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for source in selected:
                archive.write(source, "dev-sequence-bundle/" + source.relative_to(BUNDLE).as_posix())
            archive.writestr("dev-sequence-bundle/package-manifest.json", json.dumps(submanifest, ensure_ascii=False, indent=2) + "\n")
        target.with_suffix(".zip.sha256").write_text(sha(target) + "  " + target.name + "\n", encoding="utf-8")
        print(target)


if __name__ == "__main__":
    main()
