import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from app.models import MetaField
from app.services import automation_engine as engine


class WatchColumnsTests(unittest.TestCase):
    def setUp(self):
        self.fields = [MetaField(field_name=name, field_type='text', data_type='varchar') for name in ('product', 'status')]
        self.mock = patch.object(engine, 'get_meta_fields', return_value=self.fields)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def matches(self, trigger, changed, after=None):
        rule = SimpleNamespace(table_id=1, trigger_config={'type': 'recordUpdated', **trigger})
        return engine._trigger_matches(None, rule, {'actor_type': 'user', 'type': 'recordUpdated',
            'changed': changed, 'after': after or {'product': 'A', 'status': 'ready'}})

    def test_conditions_apply_only_to_changed_columns_with_or_semantics(self):
        trigger = {'watchMode': 'specified', 'watchConditions': [
            {'fieldId': 'product', 'operator': 'eq', 'value': 'A'},
            {'fieldId': 'status', 'operator': 'eq', 'value': 'ready'}]}
        self.assertTrue(self.matches(trigger, ['product']))
        self.assertTrue(self.matches(trigger, ['status'], {'product': 'B', 'status': 'ready'}))
        self.assertFalse(self.matches(trigger, ['product'], {'product': 'B', 'status': 'ready'}))
        self.assertFalse(self.matches(trigger, []))
        trigger['filter'] = {'conditions': [{'fieldId': 'status', 'operator': 'eq', 'value': 'closed'}]}
        self.assertFalse(self.matches(trigger, ['product']))

    def test_legacy_any_and_empty_specified(self):
        self.assertTrue(self.matches({'watchFields': ['product']}, ['product']))
        self.assertFalse(self.matches({'watchFields': ['product']}, ['status']))
        self.assertTrue(self.matches({'watchMode': 'any'}, ['status']))
        self.assertFalse(self.matches({'watchMode': 'specified', 'watchConditions': []}, ['product']))
        self.assertFalse(self.matches({'watchFields': ['removed']}, ['removed']))

    def test_enabled_rule_rejects_incomplete_or_unknown_columns(self):
        for conditions in ([], [{'fieldId': None}], [{'fieldId': 'removed', 'operator': 'changed'}],
                           [{'fieldId': 'product', 'operator': 'eq'}]):
            with self.assertRaises(HTTPException) as caught:
                engine.validate_rule(None, SimpleNamespace(id=1), {
                    'trigger': {'type': 'recordUpdated', 'watchMode': 'specified', 'watchConditions': conditions}})
            self.assertIn('指定列', caught.exception.detail)

    def test_save_round_trip_and_legacy_conversion(self):
        actions = [{'type': 'sendMessage', 'to': [1]}]
        trigger = {'type': 'recordUpdated', 'watchMode': 'specified', 'watchConditions': [
            {'fieldId': 'product', 'operator': 'contains', 'value': 'A'}]}
        saved, _ = engine.validate_rule(None, SimpleNamespace(id=1), {'trigger': trigger, 'actions': actions})
        self.assertEqual(saved['watchConditions'], trigger['watchConditions'])
        again, _ = engine.validate_rule(None, SimpleNamespace(id=1), {'trigger': saved, 'actions': actions})
        self.assertEqual(saved, again)
        legacy, _ = engine.validate_rule(None, SimpleNamespace(id=1), {
            'trigger': {'type': 'recordUpdated', 'watchFields': ['product']}, 'actions': actions})
        self.assertEqual(legacy['watchMode'], 'specified')
        self.assertEqual(legacy['watchConditions'], [{'fieldId': 'product', 'operator': 'changed'}])

    def test_runtime_guards_use_actor_changed_field_and_resulting_value(self):
        trigger = {'type': 'recordUpdated', 'watchMode': 'specified', 'watchConditions': [
            {'fieldId': 'product', 'operator': 'eq', 'value': 'A'}]}
        rule = SimpleNamespace(table_id=1, trigger_config=trigger)
        event = {'type': 'recordUpdated', 'actor_type': 'automation', 'changed': ['product'],
                 'after': {'product': 'A', 'status': 'ready'}}
        self.assertFalse(engine._trigger_matches(None, rule, event))
        trigger['triggerByAutomation'] = True
        self.assertTrue(engine._trigger_matches(None, rule, event))
        self.assertFalse(engine._trigger_matches(None, rule, {**event, 'changed': ['status']}))
        self.assertFalse(engine._trigger_matches(None, rule, {**event, 'after': {'product': 'B'}}))

    def test_identical_writes_and_depth_limit_do_not_dispatch(self):
        from app.services import smart_events
        table = SimpleNamespace(id=1)
        with patch.object(smart_events, 'submit') as submit:
            smart_events.record_updated(None, table, {'id': 1, 'product': 'A'},
                                        {'id': 1, 'product': 'A'}, ['product'], actor_type='automation')
            submit.assert_not_called()
            smart_events.record_updated(None, table, {'id': 1, 'product': 'A'},
                                        {'id': 1, 'product': 'B'}, ['product'], actor_type='automation',
                                        depth=smart_events.MAX_DEPTH + 1)
            submit.assert_not_called()
