import unittest
from pathlib import Path

import yaml


class ReleaseWorkflowTests(unittest.TestCase):
    def test_ci_runs_tests_on_three_operating_systems(self):
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
        matrix = workflow["jobs"]["test"]["strategy"]["matrix"]["os"]
        self.assertEqual(set(matrix), {"ubuntu-latest", "macos-latest", "windows-latest"})

    def test_tag_release_builds_native_artifacts_and_publishes_checksums(self):
        text = Path(".github/workflows/release.yml").read_text()
        for value in ("v*", "macos-latest", "windows-latest", "build_desktop.py", "check_repository_safety.py", "*.sha256", "softprops/action-gh-release"):
            self.assertIn(value, text)
        self.assertIn("contains(github.ref_name, '-')", text)


if __name__ == "__main__":
    unittest.main()
