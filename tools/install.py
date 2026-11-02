#!/usr/bin/env python3
"""Install the owned suite, optionally selecting stages. No overwrite or network."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent
NAMES = {"prd": "requirements", "ui": "ui", "proto": "prototype", "tech": "tech", "code": "code", "test": "test"}


def verify():
    manifest = json.loads((BUNDLE / "package-manifest.json").read_text(encoding="utf-8"))
    for rel, expected in manifest["files"].items():
        path = BUNDLE / rel
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("文件缺失或校验失败: " + rel)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dest", type=Path, required=True, help="目标 skills 目录；首次使用先不传 --apply 查看计划")
    p.add_argument("--stages", help="阶段ID列表；默认采用当前压缩包包含的阶段")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    try:
        manifest = verify()
        stages = args.stages.split(",") if args.stages else manifest.get("selectedStages", list(NAMES))
        if any(s not in NAMES for s in stages):
            raise ValueError("未知阶段")
        names = ["dev-sequence"] + ["dev-sequence-" + NAMES[s] for s in dict.fromkeys(stages)]
        dest = args.dest.expanduser().absolute()
        if dest.resolve() != dest:
            raise ValueError("目标不得使用符号链接目录")
        conflicts = [str(dest / name) for name in names if (dest / name).exists()]
        if conflicts:
            raise ValueError("目标已存在，保留原件，不覆盖: " + ", ".join(conflicts))
        print(json.dumps({"target": str(dest), "skills": names, "apply": args.apply}, ensure_ascii=False, indent=2))
        if not args.apply:
            return 0
        dest.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".dev-sequence-install-", dir=dest) as temporary:
            staging = Path(temporary)
            for name in names:
                shutil.copytree(BUNDLE / "skills" / name, staging / name, symlinks=False)
            installed = []
            try:
                for name in names:
                    if (dest / name).exists():
                        raise ValueError("安装时目标发生冲突: " + name)
                    # Renames are only for freshly staged owned directories.
                    os.rename(staging / name, dest / name)
                    installed.append(dest / name)
            except Exception:
                for path in installed:
                    shutil.rmtree(path)
                raise
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
