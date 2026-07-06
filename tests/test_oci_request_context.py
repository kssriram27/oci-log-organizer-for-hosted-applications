import unittest
from unittest.mock import patch

from backend.main import LogLookupRequest, SettingsModel, model_to_dict, post_log_groups, post_logs


class OciRequestContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SettingsModel(
            profile="DEFAULT",
            region="ap-hyderabad-1",
            compartment_id="ocid1.compartment.oc1..gc3",
        )

    @patch("backend.main.list_log_groups")
    def test_log_groups_use_request_settings(self, list_log_groups) -> None:
        list_log_groups.return_value = {"provider": "sdk", "data": [], "errors": []}

        result = post_log_groups(self.settings)

        passed_settings = list_log_groups.call_args.args[0]
        self.assertEqual(passed_settings["profile"], "DEFAULT")
        self.assertEqual(passed_settings["region"], "ap-hyderabad-1")
        self.assertEqual(passed_settings["compartment_id"], "ocid1.compartment.oc1..gc3")
        self.assertEqual(result["connection_context"]["region"], "ap-hyderabad-1")

    @patch("backend.main.list_logs")
    def test_logs_use_request_settings(self, list_logs) -> None:
        list_logs.return_value = {"provider": "sdk", "data": [], "errors": []}

        result = post_logs(LogLookupRequest(log_group_id="ocid1.loggroup.oc1.ap-hyderabad-1.example", settings=self.settings))

        passed_settings, log_group_id = list_logs.call_args.args
        self.assertEqual(passed_settings["profile"], "DEFAULT")
        self.assertEqual(passed_settings["region"], "ap-hyderabad-1")
        self.assertEqual(passed_settings["compartment_id"], "ocid1.compartment.oc1..gc3")
        self.assertEqual(log_group_id, "ocid1.loggroup.oc1.ap-hyderabad-1.example")
        self.assertEqual(result["connection_context"]["profile"], "DEFAULT")

    def test_theme_preferences_survive_settings_serialization(self) -> None:
        settings = SettingsModel(
            theme="accent-dark-redwood",
            theme_style="accent-dark",
            theme_selection_by_style={"accent-dark": "accent-dark-redwood"},
        )

        serialized = model_to_dict(settings)

        self.assertEqual(serialized["theme_style"], "accent-dark")
        self.assertEqual(serialized["theme_selection_by_style"]["accent-dark"], "accent-dark-redwood")


if __name__ == "__main__":
    unittest.main()
