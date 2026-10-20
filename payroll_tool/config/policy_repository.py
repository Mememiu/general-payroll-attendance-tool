"""SQLite persistence for editable drafts and immutable policy versions."""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
from typing import Mapping
from uuid import uuid4

from payroll_tool.config.policy_models import PolicyStatus
from payroll_tool.config.policy_serialization import canonical_snapshot


class PolicyConflictError(ValueError):
    """Raised when an operation would overwrite immutable policy history."""


class PolicyIntegrityError(ValueError):
    """Raised when stored policy content fails its recorded digest."""


@dataclass(frozen=True)
class PolicyVersion:
    id: str
    policy_id: str
    name: str
    version: str
    effective_from: str
    status: PolicyStatus
    snapshot: dict[str, object]
    snapshot_sha256: str
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["status"] = self.status.value
        return result


@dataclass(frozen=True)
class CalculationRecord:
    task_id: str
    policy_version_id: str
    policy_digest: str
    payroll_month: str
    period_start: str
    period_end: str
    attendance_digest: str
    employee_payroll_digest: str
    employee_count: int
    exception_count: int
    status: str
    error_summary: str | None
    result_available: bool
    created_at: str
    completed_at: str | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class PolicyRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database.parent.chmod(0o700)
        self._initialize()
        self.database.chmod(0o600)

    def create_draft(self, name: str, version: str, effective_from: str) -> PolicyVersion:
        name = name.strip()
        version = version.strip()
        if not name or not version:
            raise ValueError("policy name, version, and effective date are required")
        effective_from = _validated_date(effective_from)
        policy_id = uuid4().hex
        version_id = uuid4().hex
        timestamp = _utc_now()
        snapshot_json, digest = _serialize_snapshot({})
        with self._connect(write=True) as connection:
            connection.execute(
                "INSERT INTO policies (id, name, created_at) VALUES (?, ?, ?)",
                (policy_id, name, timestamp),
            )
            connection.execute(
                """INSERT INTO policy_versions
                   (id, policy_id, version, effective_from, status, snapshot_json,
                    snapshot_sha256, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    policy_id,
                    version,
                    effective_from,
                    PolicyStatus.DRAFT.value,
                    snapshot_json,
                    digest,
                    timestamp,
                    timestamp,
                ),
            )
        return self.get(version_id)

    def save_draft(
        self, version_id: str, snapshot: Mapping[str, object]
    ) -> PolicyVersion:
        snapshot_json, digest = _serialize_snapshot(snapshot)
        with self._connect(write=True) as connection:
            row = connection.execute(
                """SELECT v.id, v.policy_id, p.name, v.version, v.effective_from,
                          v.status, v.snapshot_json, v.snapshot_sha256,
                          v.created_at, v.updated_at
                   FROM policy_versions v JOIN policies p ON p.id = v.policy_id
                   WHERE v.id = ?""",
                (version_id,),
            ).fetchone()
            if row is None:
                raise ValueError("policy version does not exist")
            stored = _version_from_row(row)
            if stored.status != PolicyStatus.DRAFT:
                raise PolicyConflictError("only drafts can be edited")
            connection.execute(
                """UPDATE policy_versions
                   SET snapshot_json = ?, snapshot_sha256 = ?, updated_at = ?
                   WHERE id = ? AND status = ?""",
                (
                    snapshot_json,
                    digest,
                    _utc_now(),
                    version_id,
                    PolicyStatus.DRAFT.value,
                ),
            )
        return self.get(version_id)

    def publish(
        self, version_id: str, *, expected_sha256: str | None = None
    ) -> PolicyVersion:
        return self._change_status(
            version_id,
            PolicyStatus.DRAFT,
            PolicyStatus.PUBLISHED,
            "only drafts can be published",
            expected_sha256=expected_sha256,
        )

    def retire(self, version_id: str) -> PolicyVersion:
        return self._change_status(
            version_id,
            PolicyStatus.PUBLISHED,
            PolicyStatus.RETIRED,
            "only published versions can be retired",
        )

    def clone_version(
        self, source_id: str, version: str, effective_from: str
    ) -> PolicyVersion:
        version = version.strip()
        if not version:
            raise ValueError("version and effective date are required")
        effective_from = _validated_date(effective_from)
        version_id = uuid4().hex
        timestamp = _utc_now()
        with self._connect(write=True) as connection:
            source_row = connection.execute(
                """SELECT v.id, v.policy_id, p.name, v.version, v.effective_from,
                          v.status, v.snapshot_json, v.snapshot_sha256,
                          v.created_at, v.updated_at
                   FROM policy_versions v JOIN policies p ON p.id = v.policy_id
                   WHERE v.id = ?""",
                (source_id,),
            ).fetchone()
            if source_row is None:
                raise ValueError("policy version does not exist")
            source = _version_from_row(source_row)
            if source.status not in (PolicyStatus.PUBLISHED, PolicyStatus.RETIRED):
                raise PolicyConflictError("only published or retired versions can be cloned")
            duplicate = connection.execute(
                "SELECT 1 FROM policy_versions WHERE policy_id = ? AND version = ?",
                (source.policy_id, version),
            ).fetchone()
            if duplicate is not None:
                raise PolicyConflictError("policy version already exists")
            snapshot_json, digest = _serialize_snapshot(source.snapshot)
            connection.execute(
                    """INSERT INTO policy_versions
                       (id, policy_id, version, effective_from, status, snapshot_json,
                        snapshot_sha256, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        version_id,
                        source.policy_id,
                        version,
                        effective_from,
                        PolicyStatus.DRAFT.value,
                        snapshot_json,
                        digest,
                        timestamp,
                        timestamp,
                    ),
                )
        return self.get(version_id)

    def get(self, version_id: str) -> PolicyVersion:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT v.id, v.policy_id, p.name, v.version, v.effective_from,
                          v.status, v.snapshot_json, v.snapshot_sha256,
                          v.created_at, v.updated_at
                   FROM policy_versions v
                   JOIN policies p ON p.id = v.policy_id
                   WHERE v.id = ?""",
                (version_id,),
            ).fetchone()
        if row is None:
            raise ValueError("policy version does not exist")
        return _version_from_row(row)

    def list_versions(self) -> list[PolicyVersion]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT v.id, v.policy_id, p.name, v.version, v.effective_from,
                          v.status, v.snapshot_json, v.snapshot_sha256,
                          v.created_at, v.updated_at
                   FROM policy_versions v
                   JOIN policies p ON p.id = v.policy_id
                   ORDER BY v.created_at DESC, v.id DESC"""
            ).fetchall()
        return [_version_from_row(row) for row in rows]

    def create_calculation_record(
        self,
        *,
        task_id: str,
        policy_version_id: str,
        policy_digest: str,
        payroll_month: str,
        period_start: str,
        period_end: str,
        attendance_digest: str,
        employee_payroll_digest: str,
    ) -> CalculationRecord:
        period_start = _validated_date(period_start)
        period_end = _validated_date(period_end)
        if period_start > period_end:
            raise ValueError("period start cannot be after period end")
        if len(payroll_month) != 7 or payroll_month[4] != "-":
            raise ValueError("payroll month must use YYYY-MM")
        for value, label in (
            (task_id, "task id"),
            (policy_version_id, "policy version id"),
            (policy_digest, "policy digest"),
            (attendance_digest, "attendance digest"),
            (employee_payroll_digest, "employee payroll digest"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} is required")
        timestamp = _utc_now()
        try:
            with self._connect(write=True) as connection:
                version = connection.execute(
                    "SELECT snapshot_sha256 FROM policy_versions WHERE id = ?",
                    (policy_version_id,),
                ).fetchone()
                if version is None:
                    raise ValueError("policy version does not exist")
                if version["snapshot_sha256"] != policy_digest:
                    raise PolicyIntegrityError("policy digest does not match stored version")
                connection.execute(
                    """INSERT INTO monthly_tasks
                       (id, policy_version_id, policy_digest, payroll_month,
                        period_start, period_end, attendance_digest,
                        employee_payroll_digest, employee_count, exception_count,
                        status, error_summary, result_available, created_at, completed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'running', NULL, 0, ?, NULL)""",
                    (
                        task_id, policy_version_id, policy_digest, payroll_month,
                        period_start, period_end, attendance_digest,
                        employee_payroll_digest, timestamp,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "monthly_tasks.id" in str(exc) or "UNIQUE constraint" in str(exc):
                raise PolicyConflictError("calculation record already exists") from exc
            raise
        return self.get_calculation_record(task_id)

    def complete_calculation_record(
        self,
        task_id: str,
        *,
        employee_count: int,
        exception_count: int,
        result_available: bool,
        needs_review: bool = False,
    ) -> CalculationRecord:
        if employee_count < 0 or exception_count < 0:
            raise ValueError("record counts cannot be negative")
        return self._finish_calculation_record(
            task_id,
            status="needs_review" if needs_review else "completed",
            employee_count=employee_count,
            exception_count=exception_count,
            result_available=result_available,
            error_summary=None,
        )

    def fail_calculation_record(
        self, task_id: str, error_summary: str
    ) -> CalculationRecord:
        summary = " ".join(str(error_summary).split())
        summary = re.sub(
            r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s，。；;]+",
            "[本地路径已隐藏]",
            summary,
        )[:500]
        if not summary:
            summary = "计算失败"
        return self._finish_calculation_record(
            task_id,
            status="failed",
            employee_count=0,
            exception_count=0,
            result_available=False,
            error_summary=summary,
        )

    def get_calculation_record(self, task_id: str) -> CalculationRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise ValueError("calculation record does not exist")
        return _calculation_record_from_row(row)

    def list_calculation_records(self) -> list[CalculationRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM monthly_tasks ORDER BY created_at DESC, rowid DESC"
            ).fetchall()
        return [_calculation_record_from_row(row) for row in rows]

    def _finish_calculation_record(
        self,
        task_id: str,
        *,
        status: str,
        employee_count: int,
        exception_count: int,
        result_available: bool,
        error_summary: str | None,
    ) -> CalculationRecord:
        with self._connect(write=True) as connection:
            cursor = connection.execute(
                """UPDATE monthly_tasks
                   SET status = ?, employee_count = ?, exception_count = ?,
                       error_summary = ?, result_available = ?, completed_at = ?
                   WHERE id = ? AND status = 'running'""",
                (
                    status, employee_count, exception_count, error_summary,
                    int(result_available), _utc_now(), task_id,
                ),
            )
            if cursor.rowcount != 1:
                exists = connection.execute(
                    "SELECT 1 FROM monthly_tasks WHERE id = ?", (task_id,)
                ).fetchone()
                if exists is None:
                    raise ValueError("calculation record does not exist")
                raise PolicyConflictError("calculation record is already final")
        return self.get_calculation_record(task_id)

    def restore_version(self, item: Mapping[str, object]) -> bool:
        """Restore one trusted backup row without changing its historical identity."""
        imported, _ = self.restore_versions([item])
        return imported == 1

    def restore_versions(
        self, items: list[Mapping[str, object]]
    ) -> tuple[int, int]:
        """Restore a backup batch atomically, returning imported and skipped counts."""
        prepared = [_prepare_backup_item(item) for item in items]
        imported = skipped = 0
        with self._connect(write=True) as connection:
            for item, snapshot_json, digest, status in prepared:
                by_id = connection.execute(
                    """SELECT v.id, v.policy_id, p.name, v.version, v.effective_from,
                              v.status, v.snapshot_json, v.snapshot_sha256,
                              v.created_at, v.updated_at
                       FROM policy_versions v JOIN policies p ON p.id = v.policy_id
                       WHERE v.id = ?""",
                    (item["id"],),
                ).fetchone()
                by_identity = connection.execute(
                    """SELECT id FROM policy_versions
                       WHERE policy_id = ? AND version = ?""",
                    (item["policy_id"], item["version"]),
                ).fetchone()
                if by_id is not None or by_identity is not None:
                    if by_id is not None and _version_from_row(by_id).as_dict() == dict(item):
                        skipped += 1
                        continue
                    raise PolicyConflictError(
                        "backup policy conflicts with existing history"
                    )

                policy = connection.execute(
                    "SELECT name FROM policies WHERE id = ?", (item["policy_id"],)
                ).fetchone()
                if policy is not None and policy["name"] != item["name"]:
                    raise PolicyConflictError(
                        "backup policy conflicts with existing history"
                    )
                if policy is None:
                    connection.execute(
                        "INSERT INTO policies (id, name, created_at) VALUES (?, ?, ?)",
                        (item["policy_id"], item["name"], item["created_at"]),
                    )
                connection.execute(
                    """INSERT INTO policy_versions
                       (id, policy_id, version, effective_from, status, snapshot_json,
                        snapshot_sha256, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item["id"], item["policy_id"], item["version"],
                        item["effective_from"], status.value, snapshot_json, digest,
                        item["created_at"], item["updated_at"],
                    ),
                )
                imported += 1
        return imported, skipped

    def _change_status(
        self,
        version_id: str,
        current: PolicyStatus,
        target: PolicyStatus,
        conflict_message: str,
        expected_sha256: str | None = None,
    ) -> PolicyVersion:
        with self._connect(write=True) as connection:
            row = connection.execute(
                """SELECT v.id, v.policy_id, p.name, v.version, v.effective_from,
                          v.status, v.snapshot_json, v.snapshot_sha256,
                          v.created_at, v.updated_at
                   FROM policy_versions v JOIN policies p ON p.id = v.policy_id
                   WHERE v.id = ?""",
                (version_id,),
            ).fetchone()
            if row is None:
                raise ValueError("policy version does not exist")
            stored = _version_from_row(row)
            if stored.status != current:
                raise PolicyConflictError(conflict_message)
            if expected_sha256 is not None and stored.snapshot_sha256 != expected_sha256:
                raise PolicyConflictError("policy draft changed after validation")
            connection.execute(
                """UPDATE policy_versions SET status = ?, updated_at = ?
                   WHERE id = ? AND status = ?""",
                (target.value, _utc_now(), version_id, current.value),
            )
        return self.get(version_id)

    @staticmethod
    def _raise_missing_or_conflict(
        connection: sqlite3.Connection, version_id: str, message: str
    ) -> None:
        exists = connection.execute(
            "SELECT 1 FROM policy_versions WHERE id = ?", (version_id,)
        ).fetchone()
        if exists is None:
            raise ValueError("policy version does not exist")
        raise PolicyConflictError(message)

    @contextmanager
    def _connect(self, *, write: bool = False):
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except Exception:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        statements = (
                """CREATE TABLE IF NOT EXISTS policies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS policy_versions (
                    id TEXT PRIMARY KEY,
                    policy_id TEXT NOT NULL REFERENCES policies(id),
                    version TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'retired')),
                    snapshot_json TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (policy_id, version)
                )""",
                """CREATE TABLE IF NOT EXISTS monthly_tasks (
                    id TEXT PRIMARY KEY,
                    policy_version_id TEXT NOT NULL REFERENCES policy_versions(id),
                    payroll_month TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )""",
        )
        with self._connect(write=True) as connection:
            for statement in statements:
                connection.execute(statement)
            existing = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(monthly_tasks)")
            }
            additions = {
                "policy_digest": "TEXT NOT NULL DEFAULT ''",
                "attendance_digest": "TEXT NOT NULL DEFAULT ''",
                "employee_payroll_digest": "TEXT NOT NULL DEFAULT ''",
                "employee_count": "INTEGER NOT NULL DEFAULT 0",
                "exception_count": "INTEGER NOT NULL DEFAULT 0",
                "error_summary": "TEXT",
                "result_available": "INTEGER NOT NULL DEFAULT 0",
                "completed_at": "TEXT",
            }
            for name, declaration in additions.items():
                if name not in existing:
                    connection.execute(
                        f"ALTER TABLE monthly_tasks ADD COLUMN {name} {declaration}"
                    )
            connection.execute(
                """UPDATE monthly_tasks
                   SET policy_digest = (
                       SELECT snapshot_sha256 FROM policy_versions
                       WHERE policy_versions.id = monthly_tasks.policy_version_id
                   )
                   WHERE policy_digest = ''
                     AND EXISTS (
                       SELECT 1 FROM policy_versions
                       WHERE policy_versions.id = monthly_tasks.policy_version_id
                     )"""
            )


def _prepare_backup_item(
    item: Mapping[str, object],
) -> tuple[Mapping[str, object], str, str, PolicyStatus]:
    required = {
        "id", "policy_id", "name", "version", "effective_from", "status",
        "snapshot", "snapshot_sha256", "created_at", "updated_at",
    }
    if set(item) != required:
        raise ValueError("backup policy fields are invalid")
    text_fields = required - {"snapshot"}
    if any(not isinstance(item[field], str) or not item[field] for field in text_fields):
        raise ValueError("backup policy fields are invalid")
    if not isinstance(item["snapshot"], Mapping):
        raise ValueError("backup policy snapshot must be an object")
    _validated_date(item["effective_from"])
    try:
        status = PolicyStatus(item["status"])
        datetime.fromisoformat(item["created_at"])
        datetime.fromisoformat(item["updated_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("backup policy metadata is invalid") from exc
    snapshot_json, digest = _serialize_snapshot(item["snapshot"])
    if digest != item["snapshot_sha256"]:
        raise PolicyIntegrityError("backup policy snapshot integrity check failed")
    return item, snapshot_json, digest, status


def _serialize_snapshot(snapshot: Mapping[str, object]) -> tuple[str, str]:
    if not isinstance(snapshot, Mapping):
        raise TypeError("policy snapshot must be a mapping")
    _require_json_value(snapshot, "$")
    try:
        snapshot_json = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TypeError("policy drafts must contain JSON-compatible values") from exc
    return snapshot_json, canonical_snapshot(snapshot).sha256


def _version_from_row(row: sqlite3.Row) -> PolicyVersion:
    try:
        snapshot = json.loads(row["snapshot_json"])
        actual_digest = canonical_snapshot(snapshot).sha256
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise PolicyIntegrityError("policy snapshot integrity check failed") from exc
    if actual_digest != row["snapshot_sha256"]:
        raise PolicyIntegrityError("policy snapshot integrity check failed")
    return PolicyVersion(
        id=row["id"],
        policy_id=row["policy_id"],
        name=row["name"],
        version=row["version"],
        effective_from=row["effective_from"],
        status=PolicyStatus(row["status"]),
        snapshot=snapshot,
        snapshot_sha256=row["snapshot_sha256"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _calculation_record_from_row(row: sqlite3.Row) -> CalculationRecord:
    return CalculationRecord(
        task_id=row["id"],
        policy_version_id=row["policy_version_id"],
        policy_digest=row["policy_digest"],
        payroll_month=row["payroll_month"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        attendance_digest=row["attendance_digest"],
        employee_payroll_digest=row["employee_payroll_digest"],
        employee_count=row["employee_count"],
        exception_count=row["exception_count"],
        status=row["status"],
        error_summary=row["error_summary"],
        result_available=bool(row["result_available"]),
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validated_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("effective date must use YYYY-MM-DD") from exc
    if value != parsed.isoformat():
        raise ValueError("effective date must use YYYY-MM-DD")
    return parsed.isoformat()


def _require_json_value(value: object, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not (value == value and abs(value) != float("inf")):
            raise TypeError(f"policy drafts must contain JSON-compatible values at {path}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"policy drafts must contain JSON-compatible values at {path}")
            _require_json_value(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_json_value(item, f"{path}[{index}]")
        return
    raise TypeError(f"policy drafts must contain JSON-compatible values at {path}")
