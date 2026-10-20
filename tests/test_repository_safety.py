from pathlib import Path
import subprocess
import unittest


class RepositorySafetyTests(unittest.TestCase):
    def test_repository_contains_no_spreadsheet_fixture(self):
        root = Path(__file__).parents[1]
        output = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            text=True,
        )
        files = [root / line for line in output.splitlines() if line]
        forbidden = {".xlsx", ".xls", ".csv"}

        self.assertFalse(any(path.suffix.lower() in forbidden for path in files))

    def test_repository_contains_no_company_policy_defaults(self):
        root = Path(__file__).parents[1]

        self.assertFalse((root / "configs" / "example-company").exists())


if __name__ == "__main__":
    unittest.main()
