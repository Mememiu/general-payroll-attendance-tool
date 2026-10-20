"""Guard local data compatibility and back up before adopting data."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil


CURRENT_DATA_VERSION = 1


class DataMigrationError(RuntimeError):
    pass


def ensure_data_version(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "data-version.json"
    backup = None
    if marker.exists():
        try:
            version = int(json.loads(marker.read_text(encoding="utf-8"))["version"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise DataMigrationError("本地数据版本文件损坏") from exc
        if version > CURRENT_DATA_VERSION:
            raise DataMigrationError("本地数据由更高版本创建，请安装较新的应用版本")
        if version == CURRENT_DATA_VERSION:
            return None
    else:
        database = root / "policies" / "policies.sqlite3"
        if database.exists():
            backup = _backup(root, database, marker)
    _write_marker(marker, CURRENT_DATA_VERSION)
    return backup


def _backup(root, database, marker):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = root / "backups" / stamp
    destination.mkdir(parents=True)
    shutil.copy2(database, destination / database.name)
    if marker.exists():
        shutil.copy2(marker, destination / marker.name)
    return destination


def _write_marker(path, version):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": version}, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
