import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import MetaTable, MetaField, Record
from app.services.lookup_service import _match
from app.routers import smart_records


class LookupUpdateTests(unittest.TestCase):
    def test_serial_matches_numeric_but_text_ids_remain_distinct(self):
        condition = [{'sourceFieldId': 'serial', 'rightFieldId': 'number', 'op': 'eq'}]
        self.assertTrue(_match({'number': 1.0}, {'serial': '001'}, condition, 'and'))
        self.assertFalse(_match({'number': 2}, {'serial': '001'}, condition, 'and'))
        self.assertFalse(_match({'number': '1'}, {'serial': '001'}, condition, 'and'))

    def test_update_response_includes_new_lookup_value_and_clears_old_value(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            source = MetaTable(name='lookup_source', label='Source', storage_mode='json')
            target = MetaTable(name='lookup_target', label='Target', storage_mode='json')
            db.add_all([source, target]); db.flush()
            db.add_all([
                MetaField(table_id=source.id, field_name='serial', label='Serial', data_type='serial', field_type='autoNumber'),
                MetaField(table_id=source.id, field_name='text', label='Text', data_type='text', field_type='text'),
                MetaField(table_id=target.id, field_name='number', label='Number', data_type='decimal', field_type='number'),
                MetaField(table_id=target.id, field_name='lookup', label='Lookup', data_type='json', field_type='lookup', options={
                    'sourceTableId': source.id, 'sourceFieldId': 'text', 'aggregation': 'raw',
                    'conditions': [{'sourceFieldId': 'serial', 'op': 'eq', 'rightFieldId': 'number'}]}),
                Record(table_id=source.id, data={'serial': '001', 'text': 'Matched text'}),
            ])
            row = Record(table_id=target.id, data={'number': 9})
            db.add(row); db.commit()
            access = NS(table=target, ctx=NS(user=NS(id=1, username='test')))
            with patch.object(smart_records, '_effective', return_value=NS(managed=True)), patch.object(smart_records.smart_events, 'record_updated'):
                result = smart_records.update_record(target.id, row.id, {'data': {'number': 1}}, db, access)
                self.assertEqual(result['record']['lookup'], ['Matched text'])
                result = smart_records.update_record(target.id, row.id, {'data': {'number': 2}}, db, access)
                self.assertIsNone(result['record']['lookup'])
        engine.dispose()
