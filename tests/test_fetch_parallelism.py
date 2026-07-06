import threading
import time
import unittest
from unittest.mock import patch

from backend.main import FetchFormatRequest, LogSelection, post_fetch_format
from log_organizer.session_store import session_store


class FetchParallelismTests(unittest.TestCase):
    @patch("backend.main.search_logs")
    def test_searches_run_with_bounded_parallelism(self, search_logs) -> None:
        active = 0
        peak = 0
        lock = threading.Lock()

        def delayed_search(*_args, **_kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return {"provider": "sdk", "data": {"results": []}, "errors": []}

        search_logs.side_effect = delayed_search
        session = session_store.create_session()
        try:
            result = post_fetch_format(
                FetchFormatRequest(
                    session_id=session.session_id,
                    log_group_id="ocid1.loggroup.oc1.ap-hyderabad-1.example",
                    start_time="2026-07-06T00:00:00Z",
                    end_time="2026-07-06T00:05:00Z",
                    logs=[LogSelection(id=f"log-{index}", name=f"Log {index}") for index in range(4)],
                )
            )
        finally:
            session_store.close_session(session.session_id)

        self.assertEqual(len(result["results"]), 4)
        self.assertGreaterEqual(peak, 2)
        self.assertLessEqual(peak, 3)


if __name__ == "__main__":
    unittest.main()
