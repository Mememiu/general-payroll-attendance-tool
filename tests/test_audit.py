from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from payroll_tool.audit import build_audit_manifest, build_upload_audit_manifest
from payroll_tool.importers.uploaded_inputs import CalculationInputSession


class AuditTests(unittest.TestCase):
    def test_manifest_contains_only_hashes_and_safe_metadata(self):
        manifest = build_audit_manifest(
            input_bytes=b"employee_id=E001,name=Alex,salary=12000",
            config_bytes=b"package_id=policy-v1",
            result_bytes=b"net_pay=10000",
            timestamp=datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc),
            rule_package_id="policy-v1",
            rule_version="1.0.0",
        )
        serialized = json.dumps(manifest.to_dict())

        self.assertEqual(manifest.rule_package_id, "policy-v1")
        self.assertNotIn("E001", serialized)
        self.assertNotIn("Alex", serialized)
        self.assertNotIn("12000", serialized)
        self.assertNotIn("10000", serialized)

    def test_different_uploads_produce_different_input_hashes_and_task_ids(self):
        first = build_audit_manifest(
            input_bytes=b"synthetic-file-a",
            config_bytes=b"policy",
            result_bytes=b"result",
            timestamp=datetime(2026, 8, 13, tzinfo=timezone.utc),
            rule_package_id="policy",
            rule_version="1",
        )
        second = build_audit_manifest(
            input_bytes=b"synthetic-file-b",
            config_bytes=b"policy",
            result_bytes=b"result",
            timestamp=datetime(2026, 8, 13, tzinfo=timezone.utc),
            rule_package_id="policy",
            rule_version="1",
        )

        self.assertNotEqual(first.input_sha256, second.input_sha256)
        self.assertNotEqual(first.task_id, second.task_id)

    def test_upload_audit_requires_registered_unchanged_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attendance.xlsx"
            path.write_bytes(b"synthetic upload")
            upload = CalculationInputSession().register_attendance(path)
            manifest = build_upload_audit_manifest(
                upload=upload,
                config_bytes=b"policy",
                result_bytes=b"result",
                timestamp=datetime(2026, 8, 14, tzinfo=timezone.utc),
                rule_package_id="policy",
                rule_version="1",
            )
            self.assertEqual(manifest.input_sha256, upload.sha256)

            path.write_bytes(b"replaced")
            with self.assertRaisesRegex(ValueError, "changed after upload"):
                build_upload_audit_manifest(
                    upload=upload,
                    config_bytes=b"policy",
                    result_bytes=b"result",
                    timestamp=datetime(2026, 8, 14, tzinfo=timezone.utc),
                    rule_package_id="policy",
                    rule_version="1",
                )


if __name__ == "__main__":
    unittest.main()
