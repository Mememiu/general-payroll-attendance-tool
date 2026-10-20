"""Build and archive the native desktop artifact with a checksum."""

from hashlib import sha256
from pathlib import Path
import platform
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def archive_desktop(source: Path, artifact_base: Path, system: str) -> Path:
    if system == "Darwin":
        artifact = artifact_base.with_suffix(".zip")
        subprocess.run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(source),
                str(artifact),
            ],
            check=True,
        )
        return artifact
    return Path(shutil.make_archive(str(artifact_base), "zip", source.parent, source.name))


def write_checksum(artifact: Path) -> Path:
    digest = sha256(artifact.read_bytes()).hexdigest()
    checksum = artifact.with_suffix(artifact.suffix + ".sha256")
    checksum.write_text(
        f"{digest}  {artifact.name}\n",
        encoding="ascii",
        newline="\n",
    )
    return checksum


def main():
    build = ROOT / "build"
    dist = ROOT / "dist"
    shutil.rmtree(build, ignore_errors=True)
    shutil.rmtree(dist, ignore_errors=True)
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", str(ROOT / "packaging" / "general-payroll-tool.spec")],
        cwd=ROOT,
        check=True,
    )
    system = platform.system()
    source = dist / ("通用薪酬绩效工具.app" if system == "Darwin" else "GeneralPayrollTool")
    artifact_base = dist / f"GeneralPayrollTool-{system.lower()}"
    artifact = archive_desktop(source, artifact_base, system)
    write_checksum(artifact)
    print(artifact)


if __name__ == "__main__":
    main()
