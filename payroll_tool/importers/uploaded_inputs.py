"""Strict boundary for files selected by the user in one calculation task."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class UploadedFile:
    """A file explicitly supplied to the active calculation task."""

    path: Path
    original_name: str
    sha256: str


class CalculationInputSession:
    """Allow parsers to use only attendance files registered for this task."""

    def __init__(self) -> None:
        self._attendance: dict[Path, UploadedFile] = {}

    def register_attendance(self, path: Path) -> UploadedFile:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("attendance upload must be a file")
        upload = UploadedFile(
            path=resolved,
            original_name=resolved.name,
            sha256=_file_sha256(resolved),
        )
        self._attendance[resolved] = upload
        return upload

    def require_attendance(self, path: Path) -> UploadedFile:
        try:
            return self._attendance[path.resolve(strict=True)]
        except (FileNotFoundError, KeyError) as exc:
            raise ValueError(
                "attendance file was not registered as a current task upload"
            ) from exc


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
