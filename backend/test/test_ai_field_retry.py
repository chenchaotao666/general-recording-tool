import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import MetaField, MetaTable, Record, SmartAiRun
from app.services import ai_field_service


class AiFieldRetryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.table = MetaTable(name='ai_retry', label='AI retry', storage_mode='json')
        self.db.add(self.table)
        self.db.flush()
        self.source = MetaField(table_id=self.table.id, field_name='source', label='产品名称',
                                field_type='text', data_type='text', options={})
        self.output = MetaField(table_id=self.table.id, field_name='summary', label='产品介绍',
                                field_type='ai', data_type='text', options={
                                    'scene': 'summary', 'inputFields': ['source'], 'outputType': 'text',
                                })
        self.record = Record(table_id=self.table.id, data={'source': None, 'summary': 'Previous result'})
        self.db.add_all([self.source, self.output, self.record])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def run_row(self, **kwargs):
        ai_field_service.process(self.db, self.table.id, 'summary', [self.record.id], **kwargs)
        self.db.expire_all()
        return self.db.query(SmartAiRun).filter_by(record_id=self.record.id).one()

    def test_empty_input_reports_field_and_preserves_previous_output(self):
        with patch.object(ai_field_service, 'compute_cell') as compute:
            run = self.run_row()
        compute.assert_not_called()
        self.assertEqual(run.status, 'error')
        self.assertIn('请先填写「产品名称」', run.error)
        self.assertEqual(self.record.data['summary'], 'Previous result')
        self.assertFalse(run.billable)
        rows = [{'id': self.record.id}]
        ai_field_service.attach_status(self.db, self.table.id, [self.output], rows)
        self.assertEqual(rows[0]['__ai']['summary']['error'], run.error)

    def test_retry_after_filling_input_generates_content(self):
        self.run_row()
        self.record.data = {**self.record.data, 'source': 'Product A'}
        self.db.commit()
        provider = Mock(last_usage={'prompt_tokens': 10, 'completion_tokens': 10})
        provider.complete.return_value = '{"value": "New summary"}'
        with patch('app.services.llm.get_default_provider', return_value=provider), \
             patch.object(ai_field_service.smart_events, 'record_updated'):
            # enqueue clears the previous error before the worker runs.
            with patch.object(ai_field_service.smart_events, 'submit'):
                ai_field_service.enqueue(self.db, self.table.id, 'summary', [self.record.id])
            run = self.run_row()
        provider.complete.assert_called_once()
        self.assertIn('Product A', provider.complete.call_args.args[0])
        self.assertEqual(run.status, 'ok')
        self.assertIsNone(run.error)
        self.assertEqual(self.record.data['summary'], 'New summary')

    def test_zero_and_false_are_valid_inputs(self):
        for value in (0, False):
            with self.subTest(value=value):
                self.record.data = {'source': value, 'summary': 'Previous result'}
                self.db.commit()
                with patch.object(ai_field_service, 'compute_cell', return_value=('Previous result', True, 1)) as compute:
                    run = self.run_row()
                compute.assert_called_once()
                self.assertEqual(run.status, 'ok')

    def test_automatic_updates_keep_existing_empty_input_behavior(self):
        with patch.object(ai_field_service, 'compute_cell', return_value=(None, False, 0)), \
             patch.object(ai_field_service.smart_events, 'record_updated'):
            run = self.run_row(preserve_editor=True)
        self.assertEqual(run.status, 'ok')
        self.assertIsNone(self.record.data['summary'])


if __name__ == '__main__':
    unittest.main()
