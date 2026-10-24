import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from app.services.ai_template_compute import compute
from app.services.ai_field_service import coerce_basic
from app.services.ai_template_files import source_files


class AuditRegressions(unittest.TestCase):
    def test_json_tables_support_more_than_100_fields_without_relaxing_physical_limit(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.database import Base
        from app.schemas import FieldIn, TableCreate
        from app.services.meta_service import create_business_table, alter_business_table, get_meta_fields, MetaError, validate_fields
        engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
        fields=[FieldIn(field_name=f'field_{n}',label=f'Field {n}') for n in range(101)]
        try:
            with Session(engine) as db:
                with self.assertRaisesRegex(MetaError,'100'):
                    create_business_table(db,TableCreate(label='Physical',fields=fields,storage_mode='physical'),1,1)
                table=create_business_table(db,TableCreate(label='Wide audit',fields=fields),1,1)
                alter_business_table(db,table,[{'op':'add_field','field':{'field_name':'extra','label':'Extra'}}])
                self.assertEqual(len(get_meta_fields(db,table.id)),102)
                with self.assertRaisesRegex(MetaError,'500'):
                    validate_fields(fields*5,max_fields=500)
        finally:engine.dispose()

    def test_shipping_cannot_precede_order(self):
        with self.assertRaisesRegex(ValueError, '发货.*早于'):
            compute('orderShippingStatus', {'inputFields':['a','b']}, {'a':'2026-10-04','b':'2026-10-01'}, None)

    def test_numeric_outputs_reject_nonfinite_values(self):
        for value in (float('nan'),float('inf'),float('-inf'),'NaN','Infinity','-Infinity','1e999'):
            with self.subTest(value=value):
                self.assertIsNone(coerce_basic('number',value))

    def test_attachment_limit_is_not_silent_truncation(self):
        f=NS(field_type='file',field_name='f',table_id=7,options={})
        with patch('app.services.smart_files.locate',return_value=('path',{'table_id':7,'filename':'test.png'})):
            with self.assertRaisesRegex(ValueError,'4'):
                list(source_files(None,[f],{'f':['a','b','c','d','e']},['f']))


if __name__=='__main__':unittest.main()
