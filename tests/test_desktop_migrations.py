import json
import tempfile
import unittest
from pathlib import Path

from payroll_tool.desktop.migrations import CURRENT_DATA_VERSION, DataMigrationError, ensure_data_version


class DesktopMigrationTests(unittest.TestCase):
    def test_new_install_creates_current_marker_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ensure_data_version(root)
            ensure_data_version(root)
            self.assertEqual(json.loads((root / "data-version.json").read_text())["version"], CURRENT_DATA_VERSION)
            self.assertEqual(list((root / "backups").glob("*")), [])

    def test_unversioned_existing_database_is_backed_up_before_adoption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "policies" / "policies.sqlite3"
            database.parent.mkdir(parents=True)
            database.write_bytes(b"existing")
            backup = ensure_data_version(root)
            self.assertEqual((backup / "policies.sqlite3").read_bytes(), b"existing")

    def test_newer_data_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            (root / "data-version.json").write_text('{"version": 999}')
            with self.assertRaises(DataMigrationError):
                ensure_data_version(root)


if __name__ == "__main__":
    unittest.main()
