from pathlib import Path
from contextlib import closing
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from app import create_app
from tests.test_policy_validation import complete_policy


class PolicyApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "POLICY_DATABASE": Path(self.directory.name) / "policies.sqlite3",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["task_store"].close()
        self.directory.cleanup()

    def _create_draft(self) -> str:
        response = self.client.post(
            "/api/policies",
            json={
                "name": "公司制度",
                "version": "2026.01",
                "effective_from": "2026-01-01",
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["item"]["id"]

    def test_create_save_list_and_get_draft(self):
        version_id = self._create_draft()
        saved = self.client.put(
            f"/api/policies/{version_id}/draft", json={"snapshot": complete_policy()}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["item"]["status"], "draft")
        self.assertEqual(self.client.get("/api/policies").get_json()["items"][0]["id"], version_id)
        self.assertEqual(
            self.client.get(f"/api/policies/{version_id}").get_json()["item"]["snapshot"],
            complete_policy(),
        )

    def test_invalid_publish_returns_field_addressable_422(self):
        version_id = self._create_draft()
        response = self.client.post(f"/api/policies/{version_id}/publish")
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.get_json()["errors"][0]["field"])

    def test_valid_draft_can_be_validated_and_published(self):
        version_id = self._create_draft()
        self.client.put(
            f"/api/policies/{version_id}/draft", json={"snapshot": complete_policy()}
        )
        checked = self.client.post(f"/api/policies/{version_id}/validate")
        published = self.client.post(f"/api/policies/{version_id}/publish")
        self.assertEqual(checked.status_code, 200)
        self.assertEqual(checked.get_json()["errors"], [])
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.get_json()["item"]["status"], "published")
        self.assertEqual(len(published.get_json()["item"]["snapshot_sha256"]), 64)

    def test_published_version_update_returns_conflict(self):
        version_id = self._create_draft()
        self.client.put(
            f"/api/policies/{version_id}/draft", json={"snapshot": complete_policy()}
        )
        self.client.post(f"/api/policies/{version_id}/publish")
        response = self.client.put(
            f"/api/policies/{version_id}/draft", json={"snapshot": complete_policy()}
        )
        self.assertEqual(response.status_code, 409)

    def test_published_version_can_be_cloned_and_retired(self):
        version_id = self._create_draft()
        self.client.put(
            f"/api/policies/{version_id}/draft", json={"snapshot": complete_policy()}
        )
        self.client.post(f"/api/policies/{version_id}/publish")
        clone = self.client.post(
            f"/api/policies/{version_id}/clone",
            json={"version": "2026.07", "effective_from": "2026-07-01"},
        )
        retired = self.client.post(f"/api/policies/{version_id}/retire")
        self.assertEqual(clone.status_code, 201)
        self.assertEqual(clone.get_json()["item"]["status"], "draft")
        self.assertEqual(retired.get_json()["item"]["status"], "retired")

    def test_missing_version_and_invalid_json_are_clear(self):
        self.assertEqual(self.client.get("/api/policies/missing").status_code, 404)
        response = self.client.post(
            "/api/policies", data="not-json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.get_json()["errors"])

    def test_create_and_clone_reject_non_string_metadata(self):
        response = self.client.post(
            "/api/policies",
            json={"name": {"invalid": True}, "version": None, "effective_from": []},
        )
        self.assertEqual(response.status_code, 400)

        version_id = self._create_draft()
        clone = self.client.post(
            f"/api/policies/{version_id}/clone",
            json={"version": None, "effective_from": {"invalid": True}},
        )
        self.assertEqual(clone.status_code, 400)

    def test_damaged_draft_cannot_be_overwritten_or_retired_as_missing(self):
        version_id = self._create_draft()
        database = self.app.config["POLICY_DATABASE"]
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "UPDATE policy_versions SET snapshot_json = ? WHERE id = ?",
                ('{"damaged":true}', version_id),
            )

        save = self.client.put(
            f"/api/policies/{version_id}/draft", json={"snapshot": complete_policy()}
        )
        retire = self.client.post(f"/api/policies/{version_id}/retire")

        self.assertEqual(save.status_code, 500)
        self.assertEqual(retire.status_code, 500)
        self.assertTrue(any("integrity" in error for error in save.get_json()["errors"]))


if __name__ == "__main__":
    unittest.main()
