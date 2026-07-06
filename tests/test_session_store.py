import unittest
from pathlib import Path
from unittest.mock import patch

from backend.main import revision_changes
from log_organizer.formatter_core import FormatOptions, format_records
from log_organizer.session_store import SessionStore


def record(
    entry_id: str,
    revision: str = "service-00001",
    message: str = "hello",
    container_image: str = "sha256:abc123",
    container_name: str = "deployment-container",
) -> dict:
    return {
        "data": {
            "datetime": 1_700_000_000_000,
            "logContent": {
                "id": entry_id,
                "data": {
                    "time": "2026-07-01T10:00:00Z",
                    "message": message,
                    "content": {
                        "kubernetes": {
                            "container_name": container_name,
                            "container_image": container_image,
                            "labels": {
                                "serving.knative.dev/revision": revision,
                                "serving.knative.dev/service": "service",
                            },
                        }
                    },
                },
            },
        }
    }


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SessionStore(Path("unused-session-root"), memory_limit=1)
        self.session = self.store.create_session()

    def test_live_merge_deduplicates_oci_entry_ids(self) -> None:
        first = record("entry-1")
        second = record("entry-2")
        merged, added = self.store.merge_records([first], [first, second])
        self.assertEqual(added, 1)
        self.assertEqual([item["data"]["logContent"]["id"] for item in merged], ["entry-1", "entry-2"])

    def test_session_spills_after_memory_limit(self) -> None:
        with patch.object(self.store, "_spill_session") as spill:
            self.store.store_result(
                self.session.session_id,
                log_id="log-1",
                log_name="sample-log",
                output_format="text",
                provider="sdk",
                provider_errors=[],
                stats={},
                raw_records=[record("entry-1")],
                formatted_content="2026-07-01T10:00:00Z | hello\n",
            )
        self.assertTrue(self.session.disk_backed)
        spill.assert_called_once_with(self.session)

    def test_formatter_reports_every_selection_container(self) -> None:
        formatted = format_records([record("entry-1")], FormatOptions())
        selection = next(iter(formatted.stats.selections.values()))
        self.assertEqual(selection["container_name"], "deployment-container")
        self.assertEqual(selection["revision"], "service-00001")

    def test_formatter_marks_current_and_filtered_revisions(self) -> None:
        formatted = format_records(
            [
                record("entry-1", revision="service-00001", container_image="sha256:old", container_name="old-container"),
                record("entry-2", revision="service-00002", container_image="sha256:new", container_name="new-container"),
            ],
            FormatOptions(),
        )
        candidates = formatted.stats.deployment_candidates["service"]
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["revision"], "service-00002")
        self.assertTrue(candidates[0]["is_current"])
        self.assertFalse(candidates[0]["is_filtered_out"])
        self.assertEqual(candidates[1]["container_name"], "old-container")
        self.assertFalse(candidates[1]["is_current"])
        self.assertTrue(candidates[1]["is_filtered_out"])

    def test_revision_change_can_be_acknowledged(self) -> None:
        current = {"service": {"revision": "service-00001"}}
        latest = {"service": {"revision": "service-00002"}}
        self.assertEqual(len(revision_changes(current, latest, {})), 1)
        self.assertEqual(revision_changes(current, latest, {"service": "service-00002"}), [])


if __name__ == "__main__":
    unittest.main()
