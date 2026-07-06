import subprocess
import unittest
from unittest.mock import Mock, patch

from oci.exceptions import ServiceError

from log_organizer.oci_client import OciProviderError, _run_cli, _with_fallback


class OciProviderTests(unittest.TestCase):
    def test_service_error_does_not_retry_with_cli(self) -> None:
        sdk_call = Mock(side_effect=ServiceError(404, "NotAuthorizedOrNotFound", {}, "not found"))
        cli_call = Mock(return_value=[])

        with self.assertRaises(OciProviderError):
            _with_fallback({"provider_mode": "auto"}, sdk_call, cli_call)

        cli_call.assert_not_called()

    @patch("log_organizer.oci_client.subprocess.run")
    def test_cli_timeout_has_actionable_error(self, run) -> None:
        run.side_effect = subprocess.TimeoutExpired(["oci"], 30)

        with self.assertRaisesRegex(OciProviderError, "timed out"):
            _run_cli(["oci", "logging", "log-group", "list"])


if __name__ == "__main__":
    unittest.main()
