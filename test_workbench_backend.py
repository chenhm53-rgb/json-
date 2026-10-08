import json
import tempfile
import unittest

from workbench_backend import (
    SQLiteDatasetRepository,
    convert_as,
    parse_as_google,
    parse_as_proxy,
    parse_cookie_text,
)


class WorkbenchBackendTests(unittest.TestCase):
    def test_as_conversion_keeps_proxy_and_pairs_by_valid_rows(self):
        result = convert_as(
            "a@example.com----pass----code----ignored\nbad line\nsecond@example.com----p2----c2",
            "192.0.2.1:80:user:secret\ninvalid\n192.0.2.2:81:user2:secret2",
        )
        self.assertEqual(result["googleCount"], 2)
        self.assertEqual(result["proxyCount"], 2)
        self.assertEqual(result["rows"][0]["output"], "a@example.com--pass--code--192.0.2.1:80:user:secret")
        self.assertTrue(result["warnings"])

    def test_parsers_report_invalid_rows(self):
        self.assertEqual(len(parse_as_google("a----b----c").records), 1)
        self.assertEqual(len(parse_as_proxy("1.2.3.4:80:u:p").records), 1)
        self.assertTrue(parse_as_google("bad").warnings)
        self.assertTrue(parse_as_proxy("bad").warnings)

    def test_cookie_parser_supports_text_and_json(self):
        text = parse_cookie_text("Cookie: sid=one\nfoo=bar", "sample.any")
        self.assertEqual(len(text.records), 2)
        data = parse_cookie_text(json.dumps([{"cookie": "sid=two"}]), "sample.unknown")
        self.assertEqual(data.records[0]["cookie"], "sid=two")

    def test_sqlite_repository_round_trip(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as database:
            repository = SQLiteDatasetRepository(database.name)
            saved = repository.save({"name": "测试", "records": [{"cookie": "sid=one"}]})
            self.assertEqual(repository.get(saved["id"])["name"], "测试")
            self.assertEqual(len(repository.list()), 1)
            repository.delete(saved["id"])
            self.assertEqual(repository.list(), [])


if __name__ == "__main__":
    unittest.main()
