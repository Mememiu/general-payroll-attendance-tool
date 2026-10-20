import unittest
from pathlib import Path


class ReleaseDocumentationTests(unittest.TestCase):
    def test_install_and_upgrade_guides_cover_release_risks(self):
        install = Path("docs/INSTALL.md").read_text(encoding="utf-8")
        upgrade = Path("docs/UPGRADING.md").read_text(encoding="utf-8")
        for text in ("Gatekeeper", "SmartScreen", "127.0.0.1", "GeneralPayrollTool"):
            self.assertIn(text, install)
        for text in ("data-version.json", "backups/", "关闭 App", "数据库"):
            self.assertIn(text, upgrade)


if __name__ == "__main__":
    unittest.main()
