from pathlib import Path
from contextlib import closing
import os
import sqlite3
import stat
from tempfile import TemporaryDirectory
import unittest

from payroll_tool.config.policy_models import PolicyStatus
from payroll_tool.config.policy_serialization import canonical_snapshot
from payroll_tool.config.policy_repository import (
    PolicyConflictError,
    PolicyIntegrityError,
    PolicyRepository,
)


class PolicyRepositoryTests(unittest.TestCase):
    def test_draft_can_be_saved_and_survives_repository_restart(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "policies.sqlite3"
            repository = PolicyRepository(database)
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            saved = repository.save_draft(
                draft.id, {"company": {"monthly_pay_days": "21.5"}}
            )

            reopened = PolicyRepository(database).get(saved.id)
            self.assertEqual(reopened.status, PolicyStatus.DRAFT)
            self.assertEqual(reopened.snapshot["company"]["monthly_pay_days"], "21.5")
            self.assertEqual(len(reopened.snapshot_sha256), 64)

    def test_publish_makes_version_immutable(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            repository.save_draft(draft.id, {"company": {"monthly_pay_days": "21.5"}})
            version = repository.publish(draft.id)

            self.assertEqual(version.status, PolicyStatus.PUBLISHED)
            with self.assertRaises(PolicyConflictError):
                repository.save_draft(
                    version.id, {"company": {"monthly_pay_days": "22"}}
                )

    def test_publish_rejects_snapshot_changed_after_validation(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            validated = repository.save_draft(draft.id, {"version": 1})
            repository.save_draft(draft.id, {"version": 2})
            with self.assertRaisesRegex(PolicyConflictError, "changed after validation"):
                repository.publish(draft.id, expected_sha256=validated.snapshot_sha256)
            self.assertEqual(repository.get(draft.id).status, PolicyStatus.DRAFT)

    def test_clone_preserves_published_snapshot(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            repository.save_draft(draft.id, {"company": {"monthly_pay_days": "21.5"}})
            source = repository.publish(draft.id)

            clone = repository.clone_version(source.id, "2026.07", "2026-07-01")
            repository.save_draft(clone.id, {"company": {"monthly_pay_days": "22"}})

            self.assertEqual(
                repository.get(source.id).snapshot["company"]["monthly_pay_days"], "21.5"
            )
            self.assertEqual(repository.get(clone.id).status, PolicyStatus.DRAFT)

    def test_clone_rejects_mutable_source_draft(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            with self.assertRaisesRegex(PolicyConflictError, "published or retired"):
                repository.clone_version(draft.id, "2026.07", "2026-07-01")

    def test_duplicate_version_within_policy_is_rejected(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            source = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            repository.publish(source.id)
            with self.assertRaises(PolicyConflictError):
                repository.clone_version(source.id, "2026.01", "2026-07-01")

    def test_retire_keeps_snapshot_and_marks_published_version(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            repository.save_draft(draft.id, {"company": {"daily_minutes": 450}})
            published = repository.publish(draft.id)

            retired = repository.retire(published.id)

            self.assertEqual(retired.status, PolicyStatus.RETIRED)
            self.assertEqual(retired.snapshot, published.snapshot)

    def test_unknown_version_raises_clear_error(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            with self.assertRaisesRegex(ValueError, "does not exist"):
                repository.get("missing")

    def test_rejects_non_json_snapshot_values(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            with self.assertRaisesRegex(TypeError, "JSON-compatible"):
                repository.save_draft(draft.id, {"hours": (7, 30)})

    def test_detects_snapshot_tampering_on_read(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "policies.sqlite3"
            repository = PolicyRepository(database)
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            repository.save_draft(draft.id, {"company": {"daily_minutes": 450}})
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    "UPDATE policy_versions SET snapshot_json = ? WHERE id = ?",
                    ('{"company":{"daily_minutes":600}}', draft.id),
                )
            with self.assertRaisesRegex(PolicyIntegrityError, "integrity"):
                repository.get(draft.id)

    def test_damaged_draft_cannot_be_published_and_status_rolls_back(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "policies.sqlite3"
            repository = PolicyRepository(database)
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    "UPDATE policy_versions SET snapshot_json = ? WHERE id = ?",
                    ('{"company":{"daily_minutes":600}}', draft.id),
                )

            with self.assertRaises(PolicyIntegrityError):
                repository.publish(draft.id)

            with closing(sqlite3.connect(database)) as connection, connection:
                status = connection.execute(
                    "SELECT status FROM policy_versions WHERE id = ?", (draft.id,)
                ).fetchone()[0]
            self.assertEqual(status, PolicyStatus.DRAFT.value)

    def test_invalid_stored_json_raises_integrity_error(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "policies.sqlite3"
            repository = PolicyRepository(database)
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    "UPDATE policy_versions SET snapshot_json = ? WHERE id = ?",
                    ('{"company":', draft.id),
                )
            with self.assertRaisesRegex(PolicyIntegrityError, "integrity"):
                repository.get(draft.id)

    @unittest.skipIf(os.name == "nt", "POSIX mode bits are not Windows ACLs")
    def test_database_and_directory_are_private(self):
        with TemporaryDirectory() as root:
            directory = Path(root) / "private-policy"
            directory.mkdir(mode=0o755)
            database = directory / "policies.sqlite3"
            PolicyRepository(database)

            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o600)

    def test_effective_date_must_be_strict_iso_date(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            for invalid in (" ", "not-a-date", "2026-02-30", "2026-1-1"):
                with self.subTest(invalid=invalid):
                    with self.assertRaisesRegex(ValueError, "effective date"):
                        repository.create_draft("公司制度", "2026.01", invalid)


class CalculationRecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.repository = PolicyRepository(Path(self.directory.name) / "policies.sqlite3")
        draft = self.repository.create_draft("公司制度", "2026.08", "2026-08-01")
        self.version = self.repository.publish(draft.id)

    def tearDown(self):
        self.directory.cleanup()

    def test_record_lifecycle_preserves_identity_and_policy_digest(self):
        record = self.repository.create_calculation_record(
            task_id="task-1", policy_version_id=self.version.id,
            policy_digest=self.version.snapshot_sha256, payroll_month="2026-08",
            period_start="2026-08-01", period_end="2026-08-31",
            attendance_digest="a" * 64, employee_payroll_digest="b" * 64,
        )
        self.assertEqual(record.status, "running")
        completed = self.repository.complete_calculation_record(
            "task-1", employee_count=12, exception_count=2, result_available=True
        )
        self.assertEqual(completed.employee_count, 12)
        self.assertTrue(completed.result_available)
        self.assertIsNotNone(completed.completed_at)
        self.repository.retire(self.version.id)
        stored = self.repository.get_calculation_record("task-1")
        self.assertEqual(stored.policy_digest, self.version.snapshot_sha256)
        self.assertEqual(stored.period_start, "2026-08-01")

    def test_records_are_append_only_and_listed_newest_first(self):
        for task_id in ("task-1", "task-2"):
            self.repository.create_calculation_record(
                task_id=task_id, policy_version_id=self.version.id,
                policy_digest=self.version.snapshot_sha256, payroll_month="2026-08",
                period_start="2026-08-01", period_end="2026-08-31",
                attendance_digest="a" * 64, employee_payroll_digest="b" * 64,
            )
        with self.assertRaises(PolicyConflictError):
            self.repository.create_calculation_record(
                task_id="task-1", policy_version_id=self.version.id,
                policy_digest=self.version.snapshot_sha256, payroll_month="2026-08",
                period_start="2026-08-01", period_end="2026-08-31",
                attendance_digest="c" * 64, employee_payroll_digest="d" * 64,
            )
        self.assertEqual(
            [item.task_id for item in self.repository.list_calculation_records()],
            ["task-2", "task-1"],
        )

    def test_failed_record_keeps_sanitized_summary(self):
        self.repository.create_calculation_record(
            task_id="task-fail", policy_version_id=self.version.id,
            policy_digest=self.version.snapshot_sha256, payroll_month="2026-08",
            period_start="2026-08-01", period_end="2026-08-31",
            attendance_digest="a" * 64, employee_payroll_digest="b" * 64,
        )
        failed = self.repository.fail_calculation_record(
            "task-fail", "考勤字段缺失: /private/tmp/payroll.xlsx"
        )
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error_summary, "考勤字段缺失: [本地路径已隐藏]")
        self.assertFalse(failed.result_available)

    def test_legacy_monthly_task_migration_backfills_policy_digest(self):
        database = Path(self.directory.name) / "legacy.sqlite3"
        connection = sqlite3.connect(database)
        connection.executescript(
            """CREATE TABLE policies (
                   id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
               CREATE TABLE policy_versions (
                   id TEXT PRIMARY KEY, policy_id TEXT NOT NULL, version TEXT NOT NULL,
                   effective_from TEXT NOT NULL, status TEXT NOT NULL,
                   snapshot_json TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL,
                   created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                   UNIQUE (policy_id, version));
               CREATE TABLE monthly_tasks (
                   id TEXT PRIMARY KEY, policy_version_id TEXT NOT NULL,
                   payroll_month TEXT NOT NULL, period_start TEXT NOT NULL,
                   period_end TEXT NOT NULL, status TEXT NOT NULL,
                   created_at TEXT NOT NULL);"""
        )
        digest = canonical_snapshot({}).sha256
        connection.execute(
            "INSERT INTO policies VALUES ('policy-1', '旧制度', '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            """INSERT INTO policy_versions VALUES
               ('version-1', 'policy-1', '1.0', '2026-01-01', 'published',
                '{}', ?, '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00')""",
            (digest,),
        )
        connection.execute(
            """INSERT INTO monthly_tasks VALUES
               ('legacy-task', 'version-1', '2026-01', '2026-01-01',
                '2026-01-31', 'completed', '2026-02-01T00:00:00+00:00')"""
        )
        connection.commit()
        connection.close()

        migrated = PolicyRepository(database).get_calculation_record("legacy-task")

        self.assertEqual(migrated.policy_digest, digest)


if __name__ == "__main__":
    unittest.main()
