import unittest
from datetime import datetime, timezone

from payroll_tool.audit import build_audit_manifest
from payroll_tool.desktop.acceptance import workbook_evidence
from payroll_tool.exporters.excel import build_payroll_export


class RealDataAcceptanceTests(unittest.TestCase):
    def test_evidence_contains_hashes_and_counts_without_employee_ids_or_pay(self):
        audit = build_audit_manifest(
            input_bytes=b"a", config_bytes=b"b", result_bytes=b"c",
            timestamp=datetime.now(timezone.utc),
            rule_package_id="rules", rule_version="1",
        )
        content = build_payroll_export([
            {"employee_id": "S001", "net_pay": 100},
            {"employee_id": "S002", "net_pay": 200},
        ], audit)
        evidence = workbook_evidence(content)
        self.assertEqual(evidence["employee_count"], 2)
        self.assertEqual(evidence["sheet_names"], ["计算结果", "审计信息"])
        self.assertEqual(set(evidence), {"result_sha256", "sheet_names", "employee_count", "employee_ids_sha256"})
        serialized = str(evidence)
        self.assertNotIn("S001", serialized)


if __name__ == "__main__":
    unittest.main()
