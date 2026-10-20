"""Privacy-safe calculation audit metadata."""

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from uuid import uuid4

from payroll_tool.importers.uploaded_inputs import UploadedFile


@dataclass(frozen=True)
class AuditManifest:
    task_id: str
    timestamp: str
    rule_package_id: str
    rule_version: str
    input_sha256: str
    config_sha256: str
    result_sha256: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def build_audit_manifest(
    *,
    input_bytes: bytes,
    config_bytes: bytes,
    result_bytes: bytes,
    timestamp: datetime,
    rule_package_id: str,
    rule_version: str,
) -> AuditManifest:
    if not rule_package_id.strip() or not rule_version.strip():
        raise ValueError("rule package id and version are required for audit")
    return AuditManifest(
        task_id=uuid4().hex,
        timestamp=timestamp.isoformat(),
        rule_package_id=rule_package_id,
        rule_version=rule_version,
        input_sha256=_sha256(input_bytes),
        config_sha256=_sha256(config_bytes),
        result_sha256=_sha256(result_bytes),
    )


def build_upload_audit_manifest(
    *,
    upload: UploadedFile,
    config_bytes: bytes,
    result_bytes: bytes,
    timestamp: datetime,
    rule_package_id: str,
    rule_version: str,
) -> AuditManifest:
    if not isinstance(upload, UploadedFile):
        raise TypeError("audit requires a current-task UploadedFile")
    input_bytes = upload.path.read_bytes()
    if _sha256(input_bytes) != upload.sha256:
        raise ValueError("attendance file changed after upload registration")
    return build_audit_manifest(
        input_bytes=input_bytes,
        config_bytes=config_bytes,
        result_bytes=result_bytes,
        timestamp=timestamp,
        rule_package_id=rule_package_id,
        rule_version=rule_version,
    )


def _sha256(content: bytes) -> str:
    return sha256(content).hexdigest()
