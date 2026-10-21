import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import MetaTable, MetaField, Record, SerialCounter
from app.services import meta_service, json_store


class SerialBackfillTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.table = MetaTable(name='serial_test', label='Test', storage_mode='json')
        self.db.add(self.table)
        self.db.flush()
        self.db.add(MetaField(table_id=self.table.id, field_name='title', label='Title', data_type='text', field_type='text'))
        self.rows = [Record(table_id=self.table.id, data={'title': name}) for name in ['a', 'b']]
        self.db.add_all(self.rows)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_add_backfills_existing_rows_and_new_rows_continue_sequence(self):
        meta_service.alter_business_table(self.db, self.table, [{'op': 'add_field', 'field': {
            'field_name': 'serial_no', 'label': 'Serial', 'data_type': 'serial', 'field_type': 'autoNumber',
            'options': {'serial': {'pattern': 'N{000}', 'reset': 'never', 'allow_manual': False}},
        }}])
        self.assertEqual([r.data['serial_no'] for r in self.rows], ['N002', 'N001'])
        fields = list(self.db.scalars(select(MetaField).where(MetaField.table_id == self.table.id)))
        new = json_store.create_record(self.db, self.table, fields, {'title': 'c', 'serial_no': 'forged'})
        self.assertEqual(new['serial_no'], 'N003')
        meta_service.alter_business_table(self.db, self.table, [{'op': 'update_field', 'field_name': 'serial_no',
            'options': {'serial': {'pattern': 'NEW{000}', 'reset': 'never', 'allow_manual': False}}}])
        self.assertEqual([r.data['serial_no'] for r in self.rows], ['NEW002', 'NEW001'])
        self.assertEqual(json_store.create_record(self.db, self.table, fields, {})['serial_no'], 'NEW004')
        # A title-only edit must preserve values and the running counter.
        meta_service.alter_business_table(self.db, self.table, [{'op': 'update_field', 'field_name': 'serial_no',
            'label': 'Renamed', 'options': {'serial': {'pattern': 'NEW{000}', 'reset': 'never', 'allow_manual': False}}}])
        self.assertEqual([r.data['serial_no'] for r in self.rows], ['NEW002', 'NEW001'])
        self.assertEqual(json_store.create_record(self.db, self.table, fields, {})['serial_no'], 'NEW005')

    def test_configuring_existing_empty_serial_column_repairs_missing_values(self):
        self.db.add(MetaField(table_id=self.table.id, field_name='serial_no', label='Serial',
                              data_type='serial', field_type='autoNumber'))
        self.db.commit()
        meta_service.alter_business_table(self.db, self.table, [{'op': 'update_field', 'field_name': 'serial_no',
            'options': {'serial': {'pattern': '{000}', 'reset': 'never'}}}])
        self.assertEqual([r.data['serial_no'] for r in self.rows], ['002', '001'])

    def test_switch_to_increment_preserves_sequence_after_reordering(self):
        meta_service.alter_business_table(self.db, self.table, [{'op': 'add_field', 'field': {
            'field_name': 'serial_no', 'label': 'Serial', 'data_type': 'serial', 'field_type': 'autoNumber',
            'options': {'numberType': 'custom', 'segments': [{'type': 'fixedText', 'text': 'N'},
                        {'type': 'autoIncrement', 'digits': 3}], 'serial': {'pattern': 'N{000}', 'reset': 'never'}},
        }}])
        self.rows[0].sort_index = 100
        self.db.commit()
        meta_service.alter_business_table(self.db, self.table, [{'op': 'update_field', 'field_name': 'serial_no',
            'options': {'numberType': 'autoIncrement', 'serial': {'pattern': '{0}', 'reset': 'never'}}}])
        self.assertEqual([r.data['serial_no'] for r in self.rows], ['2', '1'])
        fields = list(self.db.scalars(select(MetaField).where(MetaField.table_id == self.table.id)))
        self.assertEqual(json_store.create_record(self.db, self.table, fields, {})['serial_no'], '3')

    def test_backfill_follows_manual_row_order(self):
        self.rows[0].sort_index = 100
        self.rows[1].sort_index = 50
        self.db.commit()
        meta_service.alter_business_table(self.db, self.table, [{'op': 'add_field', 'field': {
            'field_name': 'serial_no', 'label': 'Serial', 'data_type': 'serial', 'field_type': 'autoNumber',
            'options': {'serial': {'pattern': '{000}', 'reset': 'never', 'allow_manual': False}},
        }}])
        self.assertEqual([r.data['serial_no'] for r in self.rows], ['001', '002'])

    def test_format_change_keeps_110_and_next_record_gets_111(self):
        meta_service.alter_business_table(self.db, self.table, [{'op': 'add_field', 'field': {
            'field_name': 'serial_no', 'label': 'Serial', 'data_type': 'serial', 'field_type': 'autoNumber',
            'options': {'serial': {'pattern': '{0}', 'reset': 'never'}},
        }}])
        self.rows[0].data = {**self.rows[0].data, 'serial_no': '110'}
        self.rows[0].sort_index = 100
        counter = self.db.scalar(select(SerialCounter).where(SerialCounter.table_id == self.table.id))
        counter.value = 110
        self.db.commit()
        meta_service.alter_business_table(self.db, self.table, [{'op': 'update_field', 'field_name': 'serial_no',
            'options': {'serial': {'pattern': 'N{0000}', 'reset': 'never'}}}])
        self.assertEqual(self.rows[0].data['serial_no'], 'N0110')
        fields = list(self.db.scalars(select(MetaField).where(MetaField.table_id == self.table.id)))
        self.assertEqual(json_store.create_record(self.db, self.table, fields, {})['serial_no'], 'N0111')
        meta_service.alter_business_table(self.db, self.table, [{'op': 'update_field', 'field_name': 'serial_no',
            'options': {'serial': {'pattern': '{0}', 'reset': 'never'}}}])
        self.assertEqual(self.rows[0].data['serial_no'], '110')

    def test_extract_sequence_ignores_dates_and_literal_digits(self):
        from app.services.dyn_engine import serial_sequence
        self.assertEqual(serial_sequence('2026-{YYYY}{MM}{DD}-{000}', '2026-20261021-110'), 110)
        self.assertEqual(serial_sequence('{YYYY}{MM}{DD}{000}', '20261021110'), 110)
        self.assertIsNone(serial_sequence('N{000}', 'invalid'))

    def test_convert_existing_field_to_serial_generates_new_numbers(self):
        for data_type, field_type, values in [('text', 'text', ['old text', '110']),
                                              ('int', 'number', [80, 90]),
                                              ('json', 'multiSelect', [['a'], ['b']])]:
            with self.subTest(field_type=field_type):
                field = self.db.scalar(select(MetaField).where(MetaField.field_name == 'title'))
                field.data_type = data_type
                field.field_type = field_type
                field.options = {}
                for row, value in zip(self.rows, values):
                    row.data = {'title': value}
                self.db.commit()
                meta_service.alter_business_table(self.db, self.table, [{'op': 'update_field',
                    'field_name': 'title', 'field_type': 'autoNumber', 'data_type': 'serial',
                    'options': {'numberType': 'autoIncrement', 'serial': {'pattern': '{0}', 'reset': 'never'}}}])
                self.assertEqual([r.data['title'] for r in self.rows], ['2', '1'])
                self.assertEqual(field.data_type, 'serial')
                self.assertEqual(field.field_type, 'autoNumber')

    def test_new_column_ignores_deleted_column_counter_in_display_order(self):
        self.db.add(SerialCounter(table_id=self.table.id, field_name='serial_no', period_key='', value=65))
        self.db.commit()
        meta_service.alter_business_table(self.db, self.table, [{'op': 'add_field', 'field': {
            'field_name': 'serial_no', 'label': 'Serial', 'data_type': 'serial', 'field_type': 'autoNumber',
            'options': {'numberType': 'autoIncrement', 'serial': {'pattern': '{0}', 'reset': 'never'}},
        }}])
        fields = list(self.db.scalars(select(MetaField).where(MetaField.table_id == self.table.id)))
        from app.services.pyquery import sort_records_multi
        displayed = sort_records_multi(json_store.all_dicts(self.db, self.table.id, fields), [],
                                       {f.field_name: f for f in fields})
        self.assertEqual([r['serial_no'] for r in displayed], ['1', '2'])


if __name__ == '__main__':
    unittest.main()
