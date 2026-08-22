# -*- coding: utf-8 -*-

import unittest

from table_parser import parse_table


class TableParserTests(unittest.TestCase):
    def test_csv_is_parsed_for_any_dataset(self) -> None:
        result = parse_table("production.csv", "日期,部门,产量\n2026-08-22,一车间,120\n".encode())
        self.assertEqual(result["headers"], ["日期", "部门", "产量"])
        self.assertEqual(result["rows"][0]["部门"], "一车间")

    def test_duplicate_headers_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能重复"):
            parse_table("bad.csv", "日期,日期\n1,2\n".encode())

    def test_unknown_extension_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "仅支持"):
            parse_table("data.txt", b"a,b")


if __name__ == "__main__":
    unittest.main()
