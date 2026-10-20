"""HTTP API for in-app policy draft and version management."""

from collections.abc import Mapping

from flask import Blueprint, current_app, jsonify, request

from payroll_tool.config.policy_repository import (
    PolicyConflictError,
    PolicyIntegrityError,
    PolicyRepository,
)
from payroll_tool.config.policy_validation import validate_policy


policy_api = Blueprint("policy_api", __name__, url_prefix="/api/policies")


@policy_api.errorhandler(PolicyIntegrityError)
def handle_policy_integrity_error(error: PolicyIntegrityError):
    return _error(500, str(error))


@policy_api.get("")
def list_policies():
    return jsonify(items=[item.as_dict() for item in _repository().list_versions()])


@policy_api.post("")
def create_policy():
    body = _json_body()
    if body is None:
        return _error(400, "请求内容必须是 JSON 对象")
    fields = _string_fields(body, "name", "version", "effective_from")
    if fields is None:
        return _error(400, "name、version 和 effective_from 必须是字符串")
    try:
        item = _repository().create_draft(
            fields["name"], fields["version"], fields["effective_from"]
        )
    except (TypeError, ValueError) as exc:
        return _error(400, str(exc))
    return jsonify(ok=True, item=item.as_dict()), 201


@policy_api.get("/<version_id>")
def get_policy(version_id: str):
    item, response = _find(version_id)
    return response or jsonify(ok=True, item=item.as_dict())


@policy_api.put("/<version_id>/draft")
def save_policy_draft(version_id: str):
    body = _json_body()
    if body is None or not isinstance(body.get("snapshot"), Mapping):
        return _error(400, "snapshot 必须是 JSON 对象")
    try:
        item = _repository().save_draft(version_id, body["snapshot"])
    except PolicyIntegrityError as exc:
        return _error(500, str(exc))
    except PolicyConflictError as exc:
        return _error(409, str(exc))
    except ValueError as exc:
        return _error(404, str(exc))
    except TypeError as exc:
        return _error(400, str(exc))
    return jsonify(ok=True, item=item.as_dict())


@policy_api.post("/<version_id>/validate")
def validate_policy_draft(version_id: str):
    item, response = _find(version_id)
    if response:
        return response
    errors = [issue.as_dict() for issue in validate_policy(item.snapshot)]
    return jsonify(ok=not errors, errors=errors, item=item.as_dict())


@policy_api.post("/<version_id>/publish")
def publish_policy(version_id: str):
    item, response = _find(version_id)
    if response:
        return response
    errors = [issue.as_dict() for issue in validate_policy(item.snapshot)]
    if errors:
        return jsonify(ok=False, errors=errors), 422
    try:
        published = _repository().publish(
            version_id, expected_sha256=item.snapshot_sha256
        )
    except PolicyIntegrityError:
        raise
    except PolicyConflictError as exc:
        return _error(409, str(exc))
    return jsonify(ok=True, item=published.as_dict())


@policy_api.post("/<version_id>/clone")
def clone_policy(version_id: str):
    body = _json_body()
    if body is None:
        return _error(400, "请求内容必须是 JSON 对象")
    fields = _string_fields(body, "version", "effective_from")
    if fields is None:
        return _error(400, "version 和 effective_from 必须是字符串")
    try:
        item = _repository().clone_version(
            version_id,
            fields["version"],
            fields["effective_from"],
        )
    except PolicyIntegrityError as exc:
        return _error(500, str(exc))
    except PolicyConflictError as exc:
        return _error(409, str(exc))
    except ValueError as exc:
        status = 404 if "does not exist" in str(exc) else 400
        return _error(status, str(exc))
    return jsonify(ok=True, item=item.as_dict()), 201


@policy_api.post("/<version_id>/retire")
def retire_policy(version_id: str):
    try:
        item = _repository().retire(version_id)
    except PolicyIntegrityError as exc:
        return _error(500, str(exc))
    except PolicyConflictError as exc:
        return _error(409, str(exc))
    except ValueError as exc:
        return _error(404, str(exc))
    return jsonify(ok=True, item=item.as_dict())


def _repository() -> PolicyRepository:
    return current_app.extensions["policy_repository"]


def _find(version_id: str):
    try:
        return _repository().get(version_id), None
    except PolicyIntegrityError as exc:
        return None, _error(500, str(exc))
    except ValueError as exc:
        return None, _error(404, str(exc))


def _json_body() -> dict[str, object] | None:
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else None


def _string_fields(
    body: Mapping[str, object], *names: str
) -> dict[str, str] | None:
    if any(not isinstance(body.get(name), str) for name in names):
        return None
    return {name: body[name] for name in names}


def _error(status: int, message: str):
    return jsonify(ok=False, errors=[message]), status
