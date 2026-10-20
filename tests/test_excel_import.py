from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from payroll_tool.importers.excel import import_attendance_workbook, validate_mapping
from payroll_tool.importers.uploaded_inputs import CalculationInputSession


class ExcelImportTests(unittest.TestCase):
    def test_mapping_reports_missing_uploaded_header(self):
        report = validate_mapping(
            headers=["employee_name", "work_date"],
            mapping={"employee_id": "staff_code", "work_date": "work_date"},
        )

        self.assertFalse(report.ok)
        self.assertIn("staff_code", report.errors[0])

    def test_mapping_rejects_duplicate_source_columns(self):
        report = validate_mapping(
            headers=["staff_code"],
            mapping={"employee_id": "staff_code", "manager_id": "staff_code"},
        )

        self.assertFalse(report.ok)
        self.assertIn("mapped more than once", report.errors[0])

    def test_mapping_accepts_only_explicit_current_upload_headers(self):
        report = validate_mapping(
            headers=["staff_code", "work_date", "daily_result"],
            mapping={
                "employee_id": "staff_code",
                "work_date": "work_date",
                "attendance_text": "daily_result",
            },
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.errors, ())

    def test_attendance_import_requires_employee_id_date_and_attendance_text(self):
        report = validate_mapping(
            headers=["staff_code", "work_date"],
            mapping={"employee_id": "staff_code", "work_date": "work_date"},
            required_fields={"employee_id", "work_date", "attendance_text"},
        )

        self.assertFalse(report.ok)
        self.assertTrue(any("attendance_text" in error for error in report.errors))

    def test_import_reads_only_registered_upload_and_rejects_replaced_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attendance.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["staff_code", "work_date", "daily_result"])
            sheet.append(["SYN001", "2026-08-01", "normal"])
            workbook.save(path)
            upload = CalculationInputSession().register_attendance(path)

            imported = import_attendance_workbook(
                upload,
                {
                    "employee_id": "staff_code",
                    "work_date": "work_date",
                    "attendance_text": "daily_result",
                },
            )
            self.assertEqual(imported.rows[0]["employee_id"], "SYN001")

            path.write_bytes(b"replaced after registration")
            with self.assertRaisesRegex(ValueError, "changed after upload"):
                import_attendance_workbook(upload, {
                    "employee_id": "staff_code",
                    "work_date": "work_date",
                    "attendance_text": "daily_result",
                })

    def test_import_preserves_optional_workday_type_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attendance.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["staff_code", "work_date", "daily_result", "day_type"])
            sheet.append(["SYN001", "2026-08-01", "normal", "rest_day"])
            workbook.save(path)
            upload = CalculationInputSession().register_attendance(path)

            imported = import_attendance_workbook(
                upload,
                {
                    "employee_id": "staff_code",
                    "work_date": "work_date",
                    "attendance_text": "daily_result",
                    "workday_type": "day_type",
                },
            )

            self.assertEqual(imported.rows[0]["workday_type"], "rest_day")

    def test_import_rejects_a_raw_local_path(self):
        with self.assertRaisesRegex(TypeError, "UploadedFile"):
            import_attendance_workbook(Path("local-fallback.xlsx"), {})


if __name__ == "__main__":
    unittest.main()
