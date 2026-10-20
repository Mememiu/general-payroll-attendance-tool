from pathlib import Path
import subprocess


FORBIDDEN = {".xlsx", ".xls", ".csv", ".pem", ".p12", ".key"}
root = Path(__file__).parents[1]
files = subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
bad = [name for name in files if Path(name).suffix.lower() in FORBIDDEN]
if bad:
    raise SystemExit("forbidden repository files: " + ", ".join(bad))
