import tempfile
import unittest
from pathlib import Path

from app import create_desktop_app
from payroll_tool.desktop.storage import production_config, user_data_root


class DesktopStorageTests(unittest.TestCase):
    def test_platform_paths_use_stable_application_name(self):
        self.assertEqual(user_data_root(system="Darwin", home=Path("/Users/hr")), Path("/Users/hr/Library/Application Support/GeneralPayrollTool"))
        self.assertEqual(user_data_root(system="Windows", environ={"LOCALAPPDATA": r"C:\Users\hr\AppData\Local"}), Path(r"C:\Users\hr\AppData\Local") / "GeneralPayrollTool")

    def test_production_config_keeps_all_private_data_below_root(self):
        root = Path("/private/data")
        config = production_config(root)
        self.assertEqual(config["POLICY_DATABASE"], root / "policies" / "policies.sqlite3")
        self.assertEqual(config["TASK_ROOT"], root / "tasks")
        self.assertEqual(config["RULE_PACK_ROOT"], root / "rule-packs")

    def test_desktop_app_uses_explicit_data_root(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_desktop_app(Path(directory))
            self.assertEqual(app.config["TASK_ROOT"], Path(directory) / "tasks")
            app.extensions["task_store"].close()


if __name__ == "__main__":
    unittest.main()
