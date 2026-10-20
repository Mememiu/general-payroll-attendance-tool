"""Resolve persistent, per-user storage outside the application bundle."""

import os
import platform
from pathlib import Path


APP_DIRECTORY = "GeneralPayrollTool"


def user_data_root(system=None, environ=None, home=None):
    system = system or platform.system()
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if system == "Darwin":
        return home / "Library" / "Application Support" / APP_DIRECTORY
    if system == "Windows":
        base = environ.get("LOCALAPPDATA")
        if not base:
            base = str(home / "AppData" / "Local")
        return Path(base) / APP_DIRECTORY
    return Path(environ.get("XDG_DATA_HOME", home / ".local" / "share")) / APP_DIRECTORY


def production_config(root=None):
    root = Path(root) if root is not None else user_data_root()
    return {
        "POLICY_DATABASE": root / "policies" / "policies.sqlite3",
        "TASK_ROOT": root / "tasks",
        "RULE_PACK_ROOT": root / "rule-packs",
    }
