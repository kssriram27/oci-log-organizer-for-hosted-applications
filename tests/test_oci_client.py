import unittest
from configparser import ConfigParser

from log_organizer.oci_client import _profiles_from_parser


class OciClientTests(unittest.TestCase):
    def test_profiles_from_parser_includes_default_and_named_profiles(self) -> None:
        parser = ConfigParser(interpolation=None)
        parser.read_string("[DEFAULT]\nregion=ap-hyderabad-1\n\n[WORK]\nregion=us-ashburn-1\n")

        self.assertEqual(
            _profiles_from_parser(parser),
            [
                {"name": "DEFAULT", "region": "ap-hyderabad-1"},
                {"name": "WORK", "region": "us-ashburn-1"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
