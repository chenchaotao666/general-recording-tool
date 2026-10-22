import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import MetaTable, MetaField, Record, AuditLog
from app.routers import smart_records as api
from app.services import json_store
from app.services.pyquery import sort_records_multi


class InsertTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.table = MetaTable(name="insert_test", label="Insert", storage_mode="json")
        self.db.add(self.table)
        self.db.flush()
        self.original = [Record(table_id=self.table.id, data={}) for _ in range(3)]
        self.db.add_all(self.original)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def order(self):
        rows = json_store.all_dicts(self.db, self.table.id, [], normalized=True)
        return [r["id"] for r in sort_records_multi(rows, [], {})]

    def insert(self, anchor, direction, count):
        return json_store.insert_records(self.db, self.table, [], anchor, direction, count, {}, "test", 1)

    def test_both_directions_repeat_refresh_and_regular_create(self):
        first, middle, last = self.original
        timestamp = middle.updated_at
        up = self.insert(middle, "up", 2)
        expected = [last.id, *[r["id"] for r in up], middle.id, first.id]
        self.assertEqual(self.order(), expected)
        down = self.insert(middle, "down", 3)
        expected[expected.index(middle.id) + 1:expected.index(middle.id) + 1] = [r["id"] for r in down]
        self.db.expire_all()
        self.assertEqual(self.order(), expected)
        self.assertEqual(middle.updated_at, timestamp)
        newer = json_store.create_record(self.db, self.table, [], {}, user="test", owner_id=1)
        self.assertEqual(self.order(), [newer["id"], *expected])
        self.insert(last, "up", 1)
        self.assertEqual(len(self.order()), 10)

    def test_parent_and_atomic_rollback(self):
        anchor = self.original[1]
        anchor.parent_id = self.original[0].id
        self.db.commit()
        created = self.insert(anchor, "down", 1)
        self.assertEqual(self.db.get(Record, created[0]["id"]).parent_id, anchor.parent_id)
        before = self.order()
        audits = len(list(self.db.scalars(select(AuditLog))))
        real = json_store.create_record
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("test rollback")
            return real(*args, **kwargs)

        with patch.object(json_store, "create_record", side_effect=fail_second):
            with self.assertRaises(ValueError):
                self.insert(anchor, "up", 3)
        self.assertEqual(self.order(), before)
        self.assertEqual(len(list(self.db.scalars(select(AuditLog)))), audits)

    def test_validation_and_permission(self):
        access = NS(table=self.table, ctx=NS(user=NS(id=1, username="test")))
        for count in (0, -1, 101, 1.5, True, "2"):
            with self.assertRaises(HTTPException) as error:
                api.insert_records(self.table.id, self.original[0].id, {"direction": "up", "count": count}, self.db, access)
            self.assertEqual(error.exception.status_code, 422)
        with patch.object(api, "get_meta_fields", return_value=[]), \
             patch.object(api, "_effective", return_value=NS(can_add_record=False)):
            with self.assertRaises(HTTPException) as error:
                api.insert_records(self.table.id, self.original[0].id, {"direction": "down"}, self.db, access)
            self.assertEqual(error.exception.status_code, 403)
        eff = NS(can_add_record=True, managed=False, row_viewable=lambda *a: False)
        with patch.object(api, "get_meta_fields", return_value=[]), patch.object(api, "_effective", return_value=eff):
            with self.assertRaises(HTTPException) as error:
                api.insert_records(self.table.id, self.original[0].id, {"direction": "down"}, self.db, access)
            self.assertEqual(error.exception.status_code, 404)

    def test_duplicate_inserts_below_source_and_keeps_explicit_sorting(self):
        field = MetaField(table_id=self.table.id, field_name="title", label="Title",
                          data_type="text", field_type="text", nullable=True, options={})
        self.db.add(field)
        anchor = self.original[1]
        anchor.data = {"title": "original"}
        anchor.parent_id = self.original[0].id
        self.db.commit()
        timestamp = anchor.updated_at
        access = NS(table=self.table, ctx=NS(user=NS(id=1, username="test")))
        eff = NS(can_add_record=True, field_rights_map=lambda fs: {
            "title": {"firstSubmit": True, "edit": True}})
        with patch.object(api, "_effective", return_value=eff), \
             patch.object(api.smart_events, "record_created") as event:
            first = api.duplicate_record(self.table.id, anchor.id, self.db, access)["record"]
            second = api.duplicate_record(self.table.id, anchor.id, self.db, access)["record"]
        self.db.expire_all()
        order = self.order()
        self.assertEqual(order[order.index(anchor.id) + 1:order.index(anchor.id) + 3],
                         [second["id"], first["id"]])
        for record in [first, second]:
            stored = self.db.get(Record, record["id"])
            self.assertEqual(stored.data["title"], "original")
            self.assertEqual(stored.parent_id, anchor.parent_id)
        self.assertEqual(anchor.updated_at, timestamp)
        self.assertEqual(event.call_count, 2)
        rows = json_store.all_dicts(self.db, self.table.id, [field], normalized=True)
        sorted_rows = sort_records_multi(rows, [{"fieldId": "id", "direction": "asc"}], {})
        self.assertEqual([r["id"] for r in sorted_rows], sorted(order))

    def test_api_preserves_group_and_emits_after_commit(self):
        field = MetaField(table_id=self.table.id, field_name="team", label="Team",
                          data_type="text", field_type="text", options={})
        self.db.add(field)
        anchor = self.original[1]
        anchor.data = {"team": "A"}
        self.db.commit()
        access = NS(table=self.table, ctx=NS(user=NS(id=1, username="test")))
        eff = NS(can_add_record=True, managed=True, field_rights_map=lambda fs: {
            "team": {"view": True, "firstSubmit": True, "edit": True}})
        with patch.object(api, "_effective", return_value=eff), \
             patch.object(api, "_load_effective_view", return_value=(None, {"groups": [{"fieldId": "team"}]})), \
             patch.object(api.smart_events, "record_created") as event:
            result = api.insert_records(self.table.id, anchor.id, {"direction": "down", "count": 2},
                                        self.db, access)
        self.assertEqual(event.call_count, 2)
        self.db.expire_all()
        self.assertTrue(all(self.db.get(Record, rid).data["team"] == "A" for rid in result["ids"]))
        self.assertEqual([r['id'] for r in result['records']], result['ids'])
        self.assertTrue(all(r['team'] == 'A' for r in result['records']))
        order = self.order()
        start = order.index(anchor.id) + 1
        self.assertEqual(order[start:start + 2], result["ids"])


if __name__ == "__main__":
    unittest.main()
