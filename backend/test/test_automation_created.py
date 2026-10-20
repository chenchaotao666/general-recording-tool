import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from fastapi import HTTPException

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import MetaTable, MetaField, Record, SmartAutomation, SmartAutomationRun, SmartDoc, SmartDocEntry
from app.services import automation_engine as engine
from app.routers import smart_automation as api


class CreatedAutomationTests(unittest.TestCase):
    def test_dashboard_message_button_uses_document_tenant(self):
        self.rule.tenant_id = 101
        doc = SmartDoc(tenant_id=101, name="Workspace")
        other_doc = SmartDoc(tenant_id=202, name="Other")
        self.db.add_all([doc, other_doc])
        self.db.flush()
        entry = SmartDocEntry(doc_id=doc.id, type="dashboard", name="Dashboard")
        other = SmartDocEntry(doc_id=other_doc.id, type="dashboard", name="Other")
        self.db.add_all([entry, other])
        self.db.flush()
        rc = engine.RunContext(self.db, self.rule, 0)
        def button(eid):
            return {"label": "查看", "link": {"type": "var", "var": {"kind": "dashboard", "entryId": eid}}}
        self.assertEqual(engine._button_link(rc, button(entry.id), ""), f"/smart/dashboard/{entry.id}")
        self.assertEqual(engine._button_link(rc, button(other.id), ""), "")
        self.assertEqual(engine._button_link(rc, button(99999), ""), "")
        with patch.object(engine, "notify_user") as notify:
            result, _ = engine._act_send(rc, {"channel": "docMessage", "to": [1], "buttons": [button(entry.id)]})
            self.assertEqual(result["sent"], 1)
            self.assertEqual(notify.call_args.kwargs["buttons"], [{"label": "查看", "link": f"/smart/dashboard/{entry.id}"}])

    def test_message_button_links_are_preserved_and_safe(self):
        button = engine._clean_button({"label": "查看", "link": {"type": "static", "value": "https://example.com"}})
        self.assertEqual(button["link"]["value"], "https://example.com")
        rc = engine.RunContext(self.db, self.rule, 0)
        rc.steps[1] = {"table_id": self.rule.table_id, "record": {"id": self.record.id}}
        variable = {"label": "记录", "link": {"type": "var", "var": {"kind": "step", "step": 1, "key": "recordLink"}}}
        self.assertIn(f"?record={self.record.id}", engine._button_link(rc, engine._clean_button(variable), ""))
        for url in ("javascript:alert(1)", "//example.com", "/\\example.com"):
            with self.assertRaises(HTTPException):
                engine._clean_button({"link": {"type": "static", "value": url}})

    def test_weekday_schedule_preserves_minute_and_excludes_weekends(self):
        table = self.db.get(MetaTable, self.rule.table_id)
        trig, _ = engine.validate_rule(self.db, table, {
            "trigger": {"type": "schedule", "schedule": {"freq": "weekdays", "time": "17:45"}},
            "actions": [{"type": "createRecord", "tableId": table.id, "values": []}]})
        self.assertEqual(engine.cron_kwargs(trig["schedule"]),
                         {"hour": 17, "minute": 45, "day_of_week": "mon,tue,wed,thu,fri"})

    def test_find_cannot_be_last_action(self):
        table = self.db.get(MetaTable, self.rule.table_id)
        find = {"type": "findRecords", "tableId": table.id}
        create = {"type": "createRecord", "tableId": table.id, "values": []}
        for actions in ([find], [create, find]):
            with self.assertRaises(HTTPException) as caught:
                engine.validate_rule(self.db, table, {"trigger": {"type": "recordCreated"}, "actions": actions})
            self.assertEqual(caught.exception.status_code, 400)
            self.assertIn("最后一步不能为查找记录", caught.exception.detail)
        _, actions = engine.validate_rule(self.db, table, {
            "trigger": {"type": "recordUpdated"}, "actions": [find, create]})
        self.assertEqual([a["type"] for a in actions], ["findRecords", "createRecord"])
        _, saved = engine.validate_rule(self.db, table, {
            "enabled": False, "trigger": {"type": "recordCreated"}, "actions": [find]})
        self.assertEqual(saved[0]["type"], "findRecords")

    def test_same_table_loop_only_blocks_enabling(self):
        table = self.db.get(MetaTable, self.rule.table_id)
        for trigger, action in (("recordCreated", "createRecord"), ("recordUpdated", "updateRecords")):
            payload = {"trigger": {"type": trigger}, "actions": [
                {"type": "findRecords", "tableId": table.id},
                {"type": action, "tableId": table.id, "values": []}]}
            with self.assertRaises(HTTPException) as caught:
                engine.validate_rule(self.db, table, payload)
            self.assertIn("第 3 步存在循环执行", caught.exception.detail)
            _, saved = engine.validate_rule(self.db, table, {**payload, "enabled": False})
            self.assertEqual(saved[-1]["type"], action)

    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        table = MetaTable(name="automation_test", label="Test", storage_mode="json")
        self.db.add(table)
        self.db.flush()
        self.db.add(MetaField(table_id=table.id, field_name="f_1", label="Name",
                              data_type="text", field_type="text"))
        self.rule = SmartAutomation(
            table_id=table.id, enabled=True, name="New record",
            created_at=datetime.now() - timedelta(seconds=1),
            trigger_config={"type": "recordCreated", "rowConditions": [
                {"fieldId": "f_1", "operator": "isNotEmpty"}]},
            actions=[{"type": "sendMessage"}],
        )
        self.record = Record(table_id=table.id, data={})
        self.db.add_all([self.rule, self.record])
        self.db.commit()
        self.sender = patch.dict(engine.ACTIONS, {"sendMessage": lambda *_: ({"sent": 1}, "sent")})
        self.sender.start()

    def tearDown(self):
        self.sender.stop()
        self.db.close()
        self.engine.dispose()

    def event(self, kind, before, after):
        self.record.data = after
        self.db.commit()
        engine.handle_event(self.db, {
            "type": kind, "table_id": self.record.table_id, "record_id": self.record.id,
            "before": None if before is None else {"id": self.record.id, **before},
            "after": {"id": self.record.id, **after}, "changed": ["f_1"],
            "actor_type": "user", "actor_id": None,
        })

    def runs(self):
        return self.db.query(SmartAutomationRun).all()

    def test_relative_dates_resolve_at_execution_time(self):
        context = engine.RunContext(self.db, self.rule, 0)
        for key, offset in [("today", 0), ("tomorrow", 1), ("yesterday", -1)]:
            self.assertEqual(context.resolve_raw({"kind": "time", "key": key}),
                             (date.today() + timedelta(days=offset)).isoformat())

    def test_blank_then_first_fill_runs_once(self):
        self.event("recordCreated", None, {})
        self.assertEqual(len(self.runs()), 0)
        self.event("recordUpdated", {}, {"f_1": "first"})
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual(self.runs()[0].trigger_snapshot["record"]["f_1"], "first")
        self.assertGreaterEqual(self.runs()[0].step_results[0]["duration_ms"], 0)
        self.assertIn("started_at", self.runs()[0].step_results[0])
        self.event("recordUpdated", {"f_1": "first"}, {"f_1": "second"})
        self.event("recordUpdated", {"f_1": "second"}, {})
        self.event("recordUpdated", {}, {"f_1": "third"})
        self.assertEqual(len(self.runs()), 1)

    def test_prefilled_creation_does_not_repeat_on_refill(self):
        self.event("recordCreated", None, {"f_1": "first"})
        self.event("recordUpdated", {"f_1": "first"}, {})
        self.event("recordUpdated", {}, {"f_1": "second"})
        self.assertEqual(len(self.runs()), 1)

    def test_old_records_and_disabled_rules_do_not_trigger(self):
        self.record.created_at = self.rule.created_at - timedelta(days=1)
        self.event("recordUpdated", {}, {"f_1": "old"})
        self.assertEqual(len(self.runs()), 0)
        self.rule.enabled = False
        self.event("recordCreated", None, {"f_1": "new"})
        self.assertEqual(len(self.runs()), 0)

    def test_no_required_field_does_not_trigger_on_updates(self):
        self.rule.trigger_config = {"type": "recordCreated"}
        self.event("recordCreated", None, {})
        self.event("recordUpdated", {}, {"f_1": "first"})
        self.assertEqual(len(self.runs()), 1)

    def test_filter_and_automation_actor_still_apply(self):
        self.rule.trigger_config = {**self.rule.trigger_config, "filter": {
            "conditions": [{"fieldId": "f_1", "operator": "eq", "value": "wanted"}]}}
        self.event("recordUpdated", {}, {"f_1": "other"})
        self.assertEqual(len(self.runs()), 0)
        engine.handle_event(self.db, {
            "type": "recordUpdated", "table_id": self.record.table_id,
            "record_id": self.record.id, "before": {}, "after": {"f_1": "wanted"},
            "changed": ["f_1"], "actor_type": "automation", "actor_id": None,
        })
        self.assertEqual(len(self.runs()), 0)

    def test_log_filters_pagination_and_duration_boundaries(self):
        start = datetime(2026, 10, 20, 23, 59, 0)
        for seconds, status in [(59, "success"), (60, "failed"), (180, "success"), (3600, "partial")]:
            self.db.add(SmartAutomationRun(rule_id=self.rule.id, status=status, started_at=start,
                                          finished_at=start + timedelta(seconds=seconds)))
        self.db.add(SmartAutomationRun(rule_id=self.rule.id, status="running", started_at=start))
        self.db.add(SmartAutomationRun(rule_id=self.rule.id, status="success",
                                      started_at=start + timedelta(days=1), finished_at=start + timedelta(days=1, seconds=2)))
        self.db.commit()
        with patch.object(api, "_get_rule", return_value=(self.rule, None)):
            params = dict(aid=self.rule.id, db=self.db, ctx=None, start_date=start.date(), end_date=start.date())
            result = api.list_runs(**params, limit=2, page=2)
            self.assertEqual(result["total"], 5)
            self.assertEqual(len(result["runs"]), 2)
            self.assertEqual(api.list_runs(**params, statuses="success")["total"], 2)
            for bucket in ["lt1", "1to3", "3to10", "gte60"]:
                self.assertEqual(api.list_runs(**params, duration=bucket)["total"], 1)
            self.assertEqual(api.list_runs(**params, duration="10to60")["total"], 0)


if __name__ == "__main__":
    unittest.main()
