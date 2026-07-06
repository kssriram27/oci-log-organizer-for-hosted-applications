import unittest

from log_organizer.settings_store import DEFAULT_THEME_SELECTIONS, _context_key, merge_settings


class SettingsStoreTests(unittest.TestCase):
    def test_legacy_theme_becomes_classic_selection(self) -> None:
        settings = merge_settings({"theme": "graphite-dark"})

        self.assertEqual(settings["theme"], "graphite-dark")
        self.assertEqual(settings["theme_style"], "classic")
        self.assertEqual(settings["theme_selection_by_style"]["classic"], "graphite-dark")
        self.assertEqual(
            settings["theme_selection_by_style"]["accent-light"],
            DEFAULT_THEME_SELECTIONS["accent-light"],
        )

    def test_theme_selections_are_preserved_by_style(self) -> None:
        settings = merge_settings(
            {
                "theme": "accent-dark-redwood",
                "theme_style": "accent-dark",
                "theme_selection_by_style": {
                    "classic": "graphite-dark",
                    "accent-light": "accent-light-emerald",
                    "accent-dark": "accent-dark-redwood",
                },
            }
        )

        self.assertEqual(settings["theme"], "accent-dark-redwood")
        self.assertEqual(settings["theme_style"], "accent-dark")
        self.assertEqual(settings["theme_selection_by_style"]["classic"], "graphite-dark")
        self.assertEqual(settings["theme_selection_by_style"]["accent-light"], "accent-light-emerald")
        self.assertEqual(settings["theme_selection_by_style"]["accent-dark"], "accent-dark-redwood")

    def test_legacy_global_history_seeds_only_active_context(self) -> None:
        settings = merge_settings(
            {
                "region": "ap-hyderabad-1",
                "compartment_id": "ocid1.compartment.oc1..current",
                "region_options": ["us-ashburn-1", "ap-hyderabad-1", "us-ashburn-1"],
                "compartment_id_options": ["ocid1.compartment.oc1..older"],
            }
        )

        self.assertEqual(settings["region_options"], ["ap-hyderabad-1"])
        self.assertEqual(
            settings["compartment_id_options"],
            ["ocid1.compartment.oc1..current"],
        )

    def test_oci_history_is_scoped_to_config_and_profile(self) -> None:
        default_settings = merge_settings(
            {
                "config_file": "~/.oci/config",
                "profile": "DEFAULT",
                "region": "ap-hyderabad-1",
                "compartment_id": "ocid1.compartment.oc1..gc3",
                "selected_log_group_id": "ocid1.loggroup.oc1.ap-hyderabad-1.default",
                "selected_log_group_name": "default",
            }
        )
        abg_settings = merge_settings(
            {
                **default_settings,
                "profile": "ABG",
                "region": "us-ashburn-1",
                "compartment_id": "ocid1.compartment.oc1..abg",
                "selected_log_group_id": "ocid1.loggroup.oc1.us-ashburn-1.abg",
                "selected_log_group_name": "abg",
            }
        )

        default_key = _context_key("~/.oci/config", "DEFAULT")
        abg_key = _context_key("~/.oci/config", "ABG")
        history = abg_settings["oci_context_history"]

        self.assertEqual(history[default_key]["compartment_id_options"], ["ocid1.compartment.oc1..gc3"])
        self.assertEqual(history[abg_key]["compartment_id_options"], ["ocid1.compartment.oc1..abg"])
        self.assertEqual(history[default_key]["selected_log_group_name"], "default")
        self.assertEqual(history[abg_key]["selected_log_group_name"], "abg")


if __name__ == "__main__":
    unittest.main()
