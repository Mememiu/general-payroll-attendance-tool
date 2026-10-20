from pathlib import Path
import tempfile
import unittest

from payroll_tool.importers.uploaded_inputs import CalculationInputSession


class UploadedInputTests(unittest.TestCase):
    def test_session_registers_current_upload_with_sha256(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "attendance.xlsx"
            path.write_bytes(b"synthetic attendance workbook")

            upload = CalculationInputSession().register_attendance(path)

        self.assertEqual(upload.original_name, "attendance.xlsx")
        self.assertEqual(len(upload.sha256), 64)

    def test_session_rejects_unregistered_local_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "attendance.xlsx"
            path.write_bytes(b"synthetic attendance workbook")
            session = CalculationInputSession()

            with self.assertRaisesRegex(ValueError, "current task upload"):
                session.require_attendance(path)

    def test_session_only_returns_the_registered_upload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            selected = directory / "selected.xlsx"
            other = directory / "other.xlsx"
            selected.write_bytes(b"selected")
            other.write_bytes(b"other")
            session = CalculationInputSession()
            session.register_attendance(selected)

            self.assertEqual(session.require_attendance(selected).original_name, "selected.xlsx")
            with self.assertRaisesRegex(ValueError, "current task upload"):
                session.require_attendance(other)


if __name__ == "__main__":
    unittest.main()
