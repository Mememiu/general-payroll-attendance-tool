"""Run the real App calculation path and emit privacy-safe acceptance evidence."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from app import create_desktop_app
from payroll_tool.desktop.acceptance import workbook_evidence


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attendance", type=Path, required=True)
    parser.add_argument("--payroll", type=Path, required=True)
    parser.add_argument("--policy-version", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = create_desktop_app(args.data_root)
    client = app.test_client()
    with args.attendance.open("rb") as attendance, args.payroll.open("rb") as payroll:
        response = client.post("/tasks", data={
            "policy_version_id": args.policy_version,
            "payroll_month": args.month,
            "period_start": args.start,
            "period_end": args.end,
            "attendance": (attendance, args.attendance.name),
            "employee_payroll": (payroll, args.payroll.name),
        }, content_type="multipart/form-data")
    if response.status_code != 201:
        raise SystemExit("验收计算失败：" + "；".join(response.get_json().get("errors", [])))
    payload = response.get_json()
    result = client.get(f"/tasks/{payload['task_id']}/download?token={payload['download_token']}").data
    evidence = workbook_evidence(result)
    evidence.update({
        "attendance_sha256": digest(args.attendance),
        "payroll_sha256": digest(args.payroll),
        "policy_version_id": args.policy_version,
        "payroll_month": args.month,
        "review_item_count": payload["review_item_count"],
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    app.extensions["task_store"].close()
    print(args.output)


if __name__ == "__main__":
    main()
