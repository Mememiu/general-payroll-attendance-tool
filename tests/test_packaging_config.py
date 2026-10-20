import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.build_desktop import archive_desktop, write_checksum


class PackagingConfigTests(unittest.TestCase):
    def test_project_declares_desktop_runtime_and_build_dependencies(self):
        config = Path("pyproject.toml").read_text(encoding="utf-8")
        for value in ("pywebview", "platformdirs", "PyInstaller", "general-payroll-tool = \"desktop:main\""):
            self.assertIn(value, config)

    def test_spec_bundles_ui_but_never_private_instance_data(self):
        spec = Path("packaging/general-payroll-tool.spec").read_text(encoding="utf-8")
        self.assertIn("templates", spec)
        self.assertIn("static", spec)
        self.assertNotRegex(spec, re.compile(r"['\"]instance['\"]"))
        self.assertIn("console=False", spec)
        self.assertIn("通用薪酬绩效工具", spec)

    def test_build_script_writes_sha256(self):
        script = Path("scripts/build_desktop.py").read_text(encoding="utf-8")
        self.assertIn("sha256", script)
        self.assertIn("general-payroll-tool.spec", script)

    def test_macos_archive_uses_ditto_to_preserve_app_symlinks(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "通用薪酬绩效工具.app"
            source.mkdir()
            artifact_base = root / "GeneralPayrollTool-darwin"

            with patch("scripts.build_desktop.subprocess.run") as run:
                artifact = archive_desktop(source, artifact_base, "Darwin")

            self.assertEqual(artifact, artifact_base.with_suffix(".zip"))
            run.assert_called_once_with(
                [
                    "ditto",
                    "-c",
                    "-k",
                    "--sequesterRsrc",
                    "--keepParent",
                    str(source),
                    str(artifact),
                ],
                check=True,
            )

    def test_checksum_file_always_uses_unix_newline(self):
        with TemporaryDirectory() as directory:
            artifact = Path(directory) / "app.zip"
            artifact.write_bytes(b"release")

            with patch.object(Path, "write_text") as write_text:
                checksum = write_checksum(artifact)

            self.assertEqual(checksum, artifact.with_suffix(".zip.sha256"))
            self.assertEqual(write_text.call_args.kwargs["newline"], "\n")


if __name__ == "__main__":
    unittest.main()
