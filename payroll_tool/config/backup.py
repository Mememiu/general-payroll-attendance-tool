"""Portable, integrity-checked backups for local policy history."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from payroll_tool.config.policy_repository import (
    PolicyConflictError,
    PolicyIntegrityError,
    PolicyRepository,
)


FORMAT_VERSION = 1
MAX_ARCHIVE_FILES = 2
MAX_MEMBER_BYTES = 20 * 1024 * 1024
EXPECTED_FILES = {"manifest.json", "policies.json"}


class BackupConflictError(ValueError):
    """Raised when imported history disagrees with existing immutable history."""


@dataclass(frozen=True)
class BackupImportResult:
    imported: int
    skipped: int


def export_backup(repository: PolicyRepository) -> bytes:
    policies = [item.as_dict() for item in repository.list_versions()]
    policies_bytes = _json_bytes(policies)
    manifest = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "policies_sha256": sha256(policies_bytes).hexdigest(),
        "version_count": len(policies),
    }
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("policies.json", policies_bytes)
    return output.getvalue()


def import_backup(repository: PolicyRepository, content: bytes) -> BackupImportResult:
    manifest, policies = _read_backup(content)
    if any(not isinstance(item, dict) for item in policies):
        raise ValueError("backup policies must contain objects")
    try:
        imported, skipped = repository.restore_versions(policies)
    except PolicyConflictError as exc:
        raise BackupConflictError(str(exc)) from exc
    except PolicyIntegrityError as exc:
        raise ValueError("backup integrity check failed") from exc
    return BackupImportResult(imported=imported, skipped=skipped)


def _read_backup(content: bytes) -> tuple[dict[str, object], list[object]]:
    if not isinstance(content, bytes):
        raise TypeError("backup content must be bytes")
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(infos) > MAX_ARCHIVE_FILES or set(names) != EXPECTED_FILES:
                raise ValueError("backup archive files are invalid")
            if len(names) != len(set(names)):
                raise ValueError("backup archive contains duplicate files")
            if any(item.file_size > MAX_MEMBER_BYTES for item in infos):
                raise ValueError("backup archive is too large")
            manifest_bytes = archive.read("manifest.json")
            policies_bytes = archive.read("policies.json")
    except (BadZipFile, KeyError, OSError) as exc:
        raise ValueError("backup archive is invalid") from exc
    try:
        manifest = json.loads(manifest_bytes)
        policies = json.loads(policies_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("backup JSON is invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("format_version") != FORMAT_VERSION:
        raise ValueError("backup format is not supported")
    if not isinstance(policies, list):
        raise ValueError("backup policies must be a list")
    if manifest.get("version_count") != len(policies):
        raise ValueError("backup integrity check failed")
    if manifest.get("policies_sha256") != sha256(policies_bytes).hexdigest():
        raise ValueError("backup integrity check failed")
    return manifest, policies


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
