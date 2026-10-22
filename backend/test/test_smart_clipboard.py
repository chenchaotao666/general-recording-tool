import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import MetaTable, MetaField, Record, AuditLog
from app.routers import smart_records as api
from app.services import ai_field_service, json_store, perm_service


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.table = MetaTable(name='clipboard_test', label='Clipboard', storage_mode='json')
        self.db.add(self.table)
        self.db.flush()
        self.fields = [MetaField(table_id=self.table.id, field_name=name, label=name,
            field_type=ft, data_type=dt, nullable=True, options={}) for name, ft, dt in
            [('text', 'text', 'text'), ('choice', 'singleSelect', 'text'), ('number', 'number', 'decimal'), ('formula', 'formula', 'text')]]
        self.db.add_all(self.fields)
        self.rows = [Record(table_id=self.table.id, data={'text': 'old'}) for _ in range(2)]
        self.db.add_all(self.rows)
        self.db.commit()
        self.access = NS(table=self.table, ctx=NS(user=NS(id=1, username='test')))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def paste(self, cells, eff=None, skip_invalid=False):
        with patch.object(api, '_effective', return_value=eff or perm_service.Effective(managed=True)), \
             patch.object(api.smart_events, 'record_updated') as event:
            result = api.batch_update(self.table.id, {'cells': cells, 'skipInvalid': skip_invalid}, self.db, self.access)
            self.assertEqual(event.call_count, len(result['records']))
            return result

    def test_new_options_reused_and_one_write_per_row(self):
        result = self.paste([{'id': r.id, 'field': 'choice', 'labels': ['新选项']} for r in self.rows] +
                            [{'id': self.rows[0].id, 'field': 'text', 'value': '新文本'}])
        opts = result['fieldOptions']['choice']['options']
        self.assertEqual(len(opts), 1)
        self.assertEqual(opts[0]['label'], '新选项')
        self.assertEqual([r['choice'] for r in result['records']], [opts[0]['id']] * 2)
        self.assertEqual(self.db.query(AuditLog).count(), 2)

    def test_readonly_aborts_options_and_records(self):
        with self.assertRaises(HTTPException) as error:
            self.paste([{'id': self.rows[0].id, 'field': 'choice', 'labels': ['new']},
                        {'id': self.rows[1].id, 'field': 'formula', 'value': 'bad'}])
        self.assertIn('系统自动生成', error.exception.detail)
        self.assertEqual(self.fields[1].options, {})
        self.assertEqual(self.db.query(AuditLog).count(), 0)
        self.assertEqual(self.rows[0].data, {'text': 'old'})

    def test_multiple_labels_to_single_select_adds_each_and_selects_first(self):
        self.fields[1].options = {'options': [{'id': 'existing_id', 'label': '已有项'}]}
        self.db.commit()
        result = self.paste([{'id': self.rows[0].id, 'field': 'choice',
                             'labels': ['第一项', '已有项', '第三项', '第一项']}])
        options = result['fieldOptions']['choice']['options']
        self.assertEqual([o['label'] for o in options], ['已有项', '第一项', '第三项'])
        self.assertEqual(options[0]['id'], 'existing_id')
        self.assertEqual(result['records'][0]['choice'], options[1]['id'])
        self.assertEqual(self.rows[0].data['choice'], options[1]['id'])

    def test_mid_batch_failure_rolls_back_records_options_and_audit(self):
        real = json_store.update_record
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('test failure')
            return real(*args, **kwargs)
        with patch.object(json_store, 'update_record', side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                self.paste([{'id': r.id, 'field': 'choice', 'labels': ['new']} for r in self.rows])
        self.assertEqual(self.fields[1].options, {})
        self.assertTrue(all(r.data == {'text': 'old'} for r in self.rows))
        self.assertEqual(self.db.query(AuditLog).count(), 0)

    def test_permission_denied(self):
        eff = perm_service.Effective(managed=False, profiles=[{'level': 'VIEW'}])
        with self.assertRaises(HTTPException) as error:
            self.paste([{'id': self.rows[0].id, 'field': 'text', 'value': 'new'}], eff)
        self.assertEqual(error.exception.status_code, 403)

    def test_bad_number_rolls_back_prior_row_and_new_option(self):
        with self.assertRaises(HTTPException) as error:
            self.paste([{'id': self.rows[0].id, 'field': 'choice', 'labels': ['new']},
                        {'id': self.rows[1].id, 'field': 'number', 'value': 'not a number'}])
        self.assertEqual(error.exception.detail, '粘贴内容与类型不符，请修改列类型后再试。')
        self.assertEqual(self.fields[1].options, {})
        self.assertTrue(all(r.data == {'text': 'old'} for r in self.rows))
        self.assertEqual(self.db.query(AuditLog).count(), 0)

    def test_existing_enum_and_multiselect_roundtrip(self):
        self.fields[1].field_type = 'multiSelect'
        self.fields[1].data_type = 'json'
        self.fields[1].options = {'options': [{'id': 'old_id', 'label': 'existing'}]}
        self.db.commit()
        result = self.paste([{'id': self.rows[0].id, 'field': 'choice', 'labels': ['existing', 'new', 'existing']}])
        ids = result['records'][0]['choice']
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], 'old_id')
        self.assertEqual(len(result['fieldOptions']['choice']['options']), 2)

    def test_partial_paste_preserves_rejected_cells_and_saves_valid_cells(self):
        result = self.paste([
            {'id': self.rows[0].id, 'field': 'number', 'value': 'bad'},
            {'id': self.rows[0].id, 'field': 'text', 'value': 'first'},
            {'id': self.rows[0].id, 'field': 'formula', 'value': 'bad'},
            {'id': self.rows[1].id, 'field': 'number', 'value': 42},
            {'id': self.rows[1].id, 'field': 'choice', 'labels': ['new']},
        ], skip_invalid=True)
        self.assertEqual(len(result['skipped']), 2)
        self.assertEqual(len(result['applied']), 3)
        self.assertEqual(self.rows[0].data, {'text': 'first'})
        self.assertEqual(self.rows[1].data['number'], 42)
        self.assertEqual(len(result['fieldOptions']['choice']['options']), 1)
        self.assertEqual(self.db.query(AuditLog).count(), 2)

    def test_partial_paste_skips_disabled_option_creation_without_stopping_text(self):
        self.fields[1].options = {'allowAddOptionWhenEditing': False}
        self.db.commit()
        result = self.paste([
            {'id': self.rows[0].id, 'field': 'choice', 'labels': ['new']},
            {'id': self.rows[0].id, 'field': 'text', 'value': 'updated'},
        ], skip_invalid=True)
        self.assertEqual(result['fieldOptions'], {})
        self.assertEqual(len(result['skipped']), 1)
        self.assertEqual(self.rows[0].data, {'text': 'updated'})

    def test_all_invalid_partial_paste_does_not_write_or_add_audit(self):
        result = self.paste([{'id': self.rows[0].id, 'field': 'number', 'value': 'bad'}], skip_invalid=True)
        self.assertEqual(result['records'], [])
        self.assertEqual(result['applied'], [])
        self.assertEqual(self.db.query(AuditLog).count(), 0)

    def test_copy_and_paste_keep_operator_after_automatic_ai_recalculation(self):
        ai = MetaField(table_id=self.table.id, field_name='ai_text', label='AI',
                       field_type='ai', data_type='text', nullable=True,
                       options={'scene': 'custom', 'inputFields': ['text'], 'autoUpdate': True})
        editor = MetaField(table_id=self.table.id, field_name='editor', label='Editor',
                           field_type='lastModifiedBy', data_type='text', nullable=True, options={})
        self.db.add_all([ai, editor])
        source = self.rows[0]
        source.updated_by = 99
        source.updated_by_type = 'ai'
        self.db.commit()
        with patch.object(api, '_effective', return_value=perm_service.Effective(managed=True)), \
             patch.object(api.smart_events, 'record_created'):
            duplicate = api.duplicate_record(self.table.id, source.id, self.db, self.access)['record']
        pasted = self.paste([{'id': source.id, 'field': 'text', 'value': 'pasted'}])['records'][0]
        for record in [duplicate, pasted]:
            self.assertEqual(record['editor'], 1)
            self.assertEqual(record['updated_by_type'], 'user')
        with patch.object(ai_field_service, '_is_local', return_value=True), \
             patch.object(ai_field_service, 'compute_cell', return_value=('automatic result', False, 0)), \
             patch.object(api.smart_events, 'record_updated'), \
             patch.object(api.smart_events, 'submit', side_effect=lambda fn, *args, **kwargs: fn(self.db, *args, **kwargs)):
            for record, event_type in [(duplicate, 'recordCreated'), (pasted, 'recordUpdated')]:
                ai_field_service.handle_event(self.db, {'table_id': self.table.id, 'record_id': record['id'],
                    'type': event_type, 'after': record, 'changed': ['text'], 'actor_id': 1, 'actor_type': 'user'})
        self.db.expire_all()
        for record in [duplicate, pasted]:
            stored = self.db.get(Record, record['id'])
            self.assertEqual(stored.data['ai_text'], 'automatic result')
            self.assertEqual(stored.updated_by, 1)
            self.assertEqual(stored.updated_by_type, 'user')
            self.assertEqual(json_store.get_record(self.db, self.table.id, record['id'], [editor])['editor'], 1)
        # Explicitly requested AI generation retains the AI author marker.
        with patch.object(ai_field_service, '_is_local', return_value=True), \
             patch.object(ai_field_service, 'compute_cell', return_value=('manual result', False, 0)), \
             patch.object(api.smart_events, 'record_updated'):
            ai_field_service.process(self.db, self.table.id, 'ai_text', [duplicate['id']])
        self.assertEqual(json_store.get_record(self.db, self.table.id, duplicate['id'], [editor])['editor'], '__ai__')


if __name__ == '__main__':
    unittest.main()
