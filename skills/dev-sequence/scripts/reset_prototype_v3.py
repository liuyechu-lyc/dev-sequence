#!/usr/bin/env python3
"""Reset v3 prototype source change metadata before a new iteration."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


def reset_tree(value: object) -> object:
    if isinstance(value, dict):
        result = {key: reset_tree(child) for key, child in value.items()}
        if result.get("changeType") in {"new", "modified"}:
            result["changeType"] = "existing"
        if "changeImpact" in result:
            result["changeImpact"] = "none"
        return result
    if isinstance(value, list):
        return [reset_tree(item) for item in value]
    return value


def atomic_json(path: Path, value: object) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    config_path = source / "prototype.config.json"
    paths = [config_path, *sorted((source / "specs").glob("*.json"))]
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        reset = reset_tree(value)
        if path == config_path:
            for page in reset.get("pages", []):
                page["versionChanges"] = []
            reset.setdefault("overview", {})["prototypeChangeLog"] = []
        if args.apply:
            atomic_json(path, reset)
        print(("updated " if args.apply else "would update ") + str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
