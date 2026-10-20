from datetime import date, datetime, timezone
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from payroll_tool.rule_packs import RulePackStore


class RulePackStoreTests(unittest.TestCase):
    def test_equal_system_timestamps_still_list_newest_save_first(self):
        with TemporaryDirectory() as directory, patch(
            "payroll_tool.rule_packs.datetime"
        ) as clock:
            fixed = datetime(2026, 8, 1, tzinfo=timezone.utc)
            clock.now.return_value = fixed
            clock.fromisoformat.side_effect = datetime.fromisoformat
            store = RulePackStore(directory)
            store.save(
                name="规则", version="1", effective_from=date(2026, 1, 1),
                workbook_bytes=b"one",
            )
            store.save(
                name="规则", version="2", effective_from=date(2026, 2, 1),
                workbook_bytes=b"two",
            )

            self.assertEqual([pack.version for pack in store.list()], ["2", "1"])

    def test_save_and_clone_preserves_old_rule_bytes(self):
        with TemporaryDirectory() as directory:
            store = RulePackStore(directory)
            original = store.save(
                name="广州企业员工",
                version="2026.01",
                effective_from=date(2026, 1, 1),
                workbook_bytes=b"original-rules",
            )
            replacement = store.clone(
                original.id,
                version="2026.07",
                effective_from=date(2026, 7, 1),
                workbook_bytes=b"updated-rules",
            )

            self.assertEqual(store.read_workbook(original.id), b"original-rules")
            self.assertEqual(store.read_workbook(replacement.id), b"updated-rules")
            self.assertEqual([pack.version for pack in store.list()], ["2026.07", "2026.01"])


if __name__ == "__main__":
    unittest.main()
