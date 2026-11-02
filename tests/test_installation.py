"""Install in a clean temp location and run without any installed skill sources."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ds-portable-")
        self.root = Path(self.tmp.name).resolve()
        self.bundle = self.root / "bundle"
        (self.bundle / "tools").mkdir(parents=True)
        shutil.copy2(BUNDLE / "tools/install.py", self.bundle / "tools/install.py")
        shutil.copytree(BUNDLE / "skills", self.bundle / "skills", ignore=shutil.ignore_patterns("__pycache__"))
        files = {p.relative_to(self.bundle).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.bundle.rglob("*") if p.is_file()}
        (self.bundle / "package-manifest.json").write_text(json.dumps({"files": files, "selectedStages": ["proto"]}))
        self.env = dict(os.environ, PYTHONPATH="", PYTHONDONTWRITEBYTECODE="1")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args):
        return subprocess.run([sys.executable, *map(str, args)], cwd=self.root, env=self.env, text=True, capture_output=True)

    def test_all_stage_installations_run_from_owned_resources_only(self):
        for stage, name in {"prd": "requirements", "ui": "ui", "proto": "prototype", "tech": "tech", "code": "code", "test": "test"}.items():
            dest = self.root / ("installed-" + stage)
            installed = self.run_cmd(self.bundle / "tools/install.py", "--dest", dest, "--stages", stage, "--apply")
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self.assertEqual({p.name for p in dest.iterdir()}, {"dev-sequence", "dev-sequence-" + name})
            project = self.root / ("project-" + stage)
            project.mkdir()
            result = self.run_cmd(dest / "dev-sequence/scripts/ds.py", "--project", project, "init", "--stages", stage)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "验收记录/验收记录总.html").is_file())
            status = self.run_cmd(dest / "dev-sequence/scripts/ds.py", "--project", project, "status")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)[stage]["status"], "pending")

    def test_default_subset_and_existing_install_are_preserved(self):
        dest = self.root / "installed"
        first = self.run_cmd(self.bundle / "tools/install.py", "--dest", dest, "--apply")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual({p.name for p in dest.iterdir()}, {"dev-sequence", "dev-sequence-prototype"})
        existing = dest / "dev-sequence/SKILL.md"
        existing.write_text("使用者定制内容")
        second = self.run_cmd(self.bundle / "tools/install.py", "--dest", dest, "--apply")
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(existing.read_text(), "使用者定制内容")

    def test_modified_package_is_rejected_before_install(self):
        (self.bundle / "skills/dev-sequence/SKILL.md").write_text("包被改动")
        result = self.run_cmd(self.bundle / "tools/install.py", "--dest", self.root / "installed", "--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "installed").exists())

    def test_packaging_excludes_repository_metadata_and_previous_builds(self):
        shutil.copy2(BUNDLE / "tools/package.py", self.bundle / "tools/package.py")
        metadata = self.bundle / ".git"
        metadata.mkdir()
        (metadata / "config").write_text("local repository metadata")
        output = self.bundle / "dist"
        output.mkdir()
        (output / "previous.zip").write_bytes(b"previous build")
        first = self.run_cmd(self.bundle / "tools/package.py", "--output", output)
        self.assertEqual(first.returncode, 0, first.stderr)
        manifest = (self.bundle / "package-manifest.json").read_bytes()
        second = self.run_cmd(self.bundle / "tools/package.py", "--output", output)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.bundle / "package-manifest.json").read_bytes(), manifest)
        archives = [path for path in output.glob("*.zip") if path.name != "previous.zip"]
        self.assertEqual(len(archives), 7)
        for archive_path in archives:
            with zipfile.ZipFile(archive_path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertFalse(any({".git", "dist"} & set(Path(name).parts) for name in archive.namelist()))
                saved = json.loads(archive.read("dev-sequence-bundle/package-manifest.json"))
                for rel, expected in saved["files"].items():
                    self.assertEqual(hashlib.sha256(archive.read("dev-sequence-bundle/" + rel)).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
