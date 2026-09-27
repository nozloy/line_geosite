import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from domain_rules import read_domains, verify_dat_dump, verify_srs_dump


class DomainRulesTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "line"

    def test_comments_and_sorting(self):
        self.path.write_text("# comment\ndomain:uniqlo.com\n\ndomain:asos.com # shop\n")
        self.assertEqual(read_domains(self.path), ["asos.com", "uniqlo.com"])

    def test_rejects_invalid_or_ambiguous_source(self):
        for content in (
            "", "# comment\n", "domain:https://asos.com", "keyword:asos.com",
            "full:asos.com", "domain:asos..com", "domain:-asos.com", "domain:asos.com/",
            "domain:ASOS.COM", "domain:*.asos.com", "domain:127.0.0.1",
            "domain:asos.com\ndomain:asos.com", "domain:asos.com\ndomain:www.asos.com",
        ):
            with self.subTest(content=content):
                self.path.write_text(content)
                with self.assertRaises(ValueError):
                    read_domains(self.path)

    def test_dat_requires_exact_category_and_domain_rule_type(self):
        valid = 'lists:\n  - name: "line"\n    length: 1\n    rules:\n      - "domain:asos.com"\n'
        self.path.write_text(valid)
        verify_dat_dump(self.path, ["asos.com"])
        for invalid in (
            valid.replace('"line"', '"other"'),
            valid.replace("domain:asos.com", "full:asos.com"),
            valid + '  - name: "extra"\n',
            valid.replace("asos.com", "example.com"),
        ):
            with self.subTest(invalid=invalid):
                self.path.write_text(invalid)
                with self.assertRaises(ValueError):
                    verify_dat_dump(self.path, ["asos.com"])

    def test_srs_requires_domain_suffix_and_compatible_version(self):
        valid = {"version": 2, "rules": [{"domain_suffix": ["asos.com"]}]}
        self.path.write_text(json.dumps(valid))
        verify_srs_dump(self.path, ["asos.com"])
        for invalid in (
            {"version": 5, "rules": valid["rules"]},
            {"version": 2, "rules": [{"domain": ["asos.com"]}]},
            {"version": 2, "rules": [{"domain_suffix": ["example.com"]}]},
            {"version": 2, "rules": valid["rules"] * 2},
        ):
            with self.subTest(invalid=invalid):
                self.path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    verify_srs_dump(self.path, ["asos.com"])


if __name__ == "__main__":
    unittest.main()
