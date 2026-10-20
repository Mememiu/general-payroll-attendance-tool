"""Local, versioned HR rule-pack storage."""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class RulePack:
    id: str
    name: str
    version: str
    effective_from: str
    created_at: str
    workbook_sha256: str


class RulePackStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def save(
        self, *, name: str, version: str, effective_from: date, workbook_bytes: bytes
    ) -> RulePack:
        if not name.strip() or not version.strip() or not workbook_bytes:
            raise ValueError("rule pack name, version, and workbook are required")
        created_at = datetime.now(timezone.utc)
        existing = self.list()
        if existing:
            latest = max(datetime.fromisoformat(item.created_at) for item in existing)
            if created_at <= latest:
                created_at = latest + timedelta(microseconds=1)
        pack = RulePack(
            id=uuid4().hex,
            name=name.strip(),
            version=version.strip(),
            effective_from=effective_from.isoformat(),
            created_at=created_at.isoformat(),
            workbook_sha256=sha256(workbook_bytes).hexdigest(),
        )
        directory = self.root / pack.id
        directory.mkdir(mode=0o700)
        (directory / "rules.xlsx").write_bytes(workbook_bytes)
        (directory / "metadata.json").write_text(
            json.dumps(asdict(pack), ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        return pack

    def clone(
        self, source_id: str, *, version: str, effective_from: date, workbook_bytes: bytes
    ) -> RulePack:
        return self.save(
            name=self.get(source_id).name,
            version=version,
            effective_from=effective_from,
            workbook_bytes=workbook_bytes,
        )

    def get(self, pack_id: str) -> RulePack:
        metadata = self.root / pack_id / "metadata.json"
        if not metadata.is_file():
            raise ValueError("rule pack does not exist")
        return RulePack(**json.loads(metadata.read_text(encoding="utf-8")))

    def list(self) -> list[RulePack]:
        packs = [self.get(path.name) for path in self.root.iterdir() if path.is_dir()]
        return sorted(packs, key=lambda item: item.created_at, reverse=True)

    def read_workbook(self, pack_id: str) -> bytes:
        pack = self.get(pack_id)
        content = (self.root / pack.id / "rules.xlsx").read_bytes()
        if sha256(content).hexdigest() != pack.workbook_sha256:
            raise ValueError("rule pack workbook integrity check failed")
        return content
