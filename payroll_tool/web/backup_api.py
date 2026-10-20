"""Advanced local policy backup and one-time legacy migration endpoints."""

from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from payroll_tool.config.backup import (
    BackupConflictError,
    export_backup,
    import_backup,
)
from payroll_tool.config.legacy_migration import migrate_hr_workbook
from payroll_tool.config.policy_repository import PolicyRepository


backup_api = Blueprint("backup_api", __name__, url_prefix="/api/advanced")


@backup_api.get("/policy-backup")
def download_policy_backup():
    return send_file(
        BytesIO(export_backup(_repository())),
        mimetype="application/zip",
        as_attachment=True,
        download_name="policy-backup.zip",
    )


@backup_api.post("/policy-backup/import")
def upload_policy_backup():
    upload = request.files.get("backup")
    if upload is None or not upload.filename:
        return _error(400, "请选择规则备份文件")
    if Path(upload.filename).suffix.lower() != ".zip":
        return _error(400, "规则备份仅支持 ZIP")
    try:
        result = import_backup(_repository(), upload.read())
    except BackupConflictError as exc:
        return _error(409, str(exc))
    except (TypeError, ValueError) as exc:
        return _error(400, str(exc))
    return jsonify(ok=True, imported=result.imported, skipped=result.skipped)


@backup_api.post("/migrate-legacy")
def migrate_legacy_workbook():
    name = request.form.get("name", "").strip()
    version = request.form.get("version", "").strip()
    effective_from = request.form.get("effective_from", "").strip()
    upload = request.files.get("workbook")
    if not name or not version or not effective_from:
        return _error(400, "名称、版本和生效日均为必填项")
    if upload is None or not upload.filename:
        return _error(400, "请选择旧 HR 规则工作簿")
    if Path(upload.filename).suffix.lower() != ".xlsx":
        return _error(400, "旧规则迁移仅支持 XLSX")
    try:
        migrated = migrate_hr_workbook(upload.read())
        draft = _repository().create_draft(name, version, effective_from)
        draft = _repository().save_draft(draft.id, migrated["snapshot"])
    except (TypeError, ValueError) as exc:
        return _error(400, str(exc))
    return jsonify(ok=True, requires_hr_review=True, item=draft.as_dict()), 201


def _repository() -> PolicyRepository:
    return current_app.extensions["policy_repository"]


def _error(status: int, message: str):
    return jsonify(ok=False, errors=[message]), status
