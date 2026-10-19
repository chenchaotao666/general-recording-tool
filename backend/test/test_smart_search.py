import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from fastapi import HTTPException

from app.routers import smart_records as api
from app.services.smart_format import search_text


def field(name, kind, **options):
    return NS(field_name=name, field_type=kind, options=options, label=name, data_type="text")


class SearchTests(unittest.TestCase):
    def test_formatted_values(self):
        cases = [
            ("date", "2026-10-19", {"format": "yyyy/MM/dd"}, "2026/10/19"),
            ("number", 1234.5, {"precision": 2, "thousandSeparator": True}, "1,234.50"),
            ("number", 0, {}, "0"),
            ("currency", 12, {"currencySymbol": "$"}, "$12.00"),
            ("percent", 25, {}, "25%"),
            ("checkbox", True, {}, "✓"),
            ("file", [{"name": "report.pdf"}], {}, "report.pdf"),
            ("url", {"text": "site", "url": "https://example.org"}, {}, "example.org"),
            ("ai", 12, {"outputType": "number"}, "12"),
            ("formula", 12, {}, "12"),
            ("lookup", [12, 34], {}, "34"),
        ]
        for kind, value, options, expected in cases:
            with self.subTest(kind=kind):
                self.assertIn(expected, search_text(None, field("f", kind, **options), value))
        self.assertEqual(search_text(None, field("f", "number"), None), "")

    def test_all_types_search_and_permissions(self):
        fields = [field("n", "number"), field("d", "date"), field("f", "formula"),
                  field("s", "singleSelect", options=[{"id": "opt", "label": "2026 choice"}]),
                  field("secret", "number"), field("text", "text")]
        for f in fields[:3]:
            f.data_type = "decimal" if f.field_name != "d" else "date"
        rows = [{"id": 1, "n": 2026, "d": "2026-10-19", "f": 2026,
                 "s": "opt", "secret": 2026, "text": "2026"}]
        eff = NS(managed=True, level="EDIT", field_rights_map=lambda fs: {
            f.field_name: {"view": f.field_name != "secret", "edit": True} for f in fs})
        access = NS(can_edit=True, ctx=NS(user=NS(id=1)))
        with patch.object(api, "get_meta_fields", return_value=fields), \
             patch.object(api, "_effective", return_value=eff), \
             patch.object(api, "_load_effective_view", return_value=(None, {})), \
             patch.object(api.json_store, "all_dicts", side_effect=lambda *a, **k: [dict(r) for r in rows]), \
             patch.object(api, "_inject_system_and_lookup"):
            result = api.search_replace(1, {"find": "2026"}, db=None, access=access)
        matches = {m["field"]: m for m in result["matches"]}
        self.assertEqual(set(matches), {"n", "d", "f", "s", "text"})
        self.assertTrue(matches["text"]["replaceable"])
        for name in ("n", "d", "f", "s"):
            self.assertFalse(matches[name]["replaceable"])

    def test_relation_labels_respect_target_permissions(self):
        relation = field("relation", "relation", targetTableId=2)
        access = NS(ctx=NS(user=NS(id=1)))
        label_field = field("title", "text")
        eff = NS(managed=False,
                 field_rights_map=lambda fs: {"title": {"view": True}},
                 row_viewable=lambda row, fs: row["id"] == 1)
        with patch.object(api, "get_table_access", return_value=NS(can_view=True)), \
             patch.object(api, "_effective", return_value=eff), \
             patch.object(api, "get_meta_fields", return_value=[label_field]), \
             patch.object(api.json_store, "all_dicts", return_value=[
                 {"id": 1, "title": "Visible title"}, {"id": 2, "title": "Private title"}]):
            self.assertEqual(api._search_relation_labels(None, [relation], access),
                             {2: {"1": "Visible title"}})
        with patch.object(api, "get_table_access", side_effect=HTTPException(404)):
            self.assertEqual(api._search_relation_labels(None, [relation], access), {2: {}})


if __name__ == "__main__":
    unittest.main()
