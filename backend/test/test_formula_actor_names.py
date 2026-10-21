import unittest
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import User, Tenant, TenantMember
from app.services import dyn_engine, expr, formula_tables


class FormulaActorNameTests(unittest.TestCase):
    def test_member_listjoin_uses_names_and_preserves_list_order(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        fields = [SimpleNamespace(field_name='people', field_type='member', data_type='json', options={})]
        with Session(engine) as db:
            db.add(Tenant(id=1, name='Company'))
            db.add_all([User(id=2, username='Alice'), User(id=3, username='Bob')])
            db.add_all([TenantMember(tenant_id=1, user_id=i) for i in (2, 3)])
            db.commit()
            row = {'people': [3, '2']}
            with formula_tables.scope(db, 1):
                context = dyn_engine.formula_context(fields, row)
                self.assertEqual(expr.evaluate(expr.parse('CONCAT("客户1", LISTJOIN([people], "、"))'), context), '客户1Bob、Alice')
                self.assertEqual(dyn_engine.formula_context(fields, {'people': 2})['people'], 'Alice')
                self.assertEqual(dyn_engine.formula_context(fields, {'people': []})['people'], [])
                self.assertIsNone(dyn_engine.formula_context(fields, {'people': None})['people'])
            self.assertEqual(row['people'], [3, '2'])
        engine.dispose()

    def test_formula_uses_names_without_changing_stored_actor_ids(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        fields = [SimpleNamespace(field_name=n, field_type=t, data_type='varchar', options={})
                  for n, t in [('creator', 'createdBy'), ('editor', 'lastModifiedBy')]]
        with Session(engine) as db:
            db.add(Tenant(id=1, name='Company'))
            db.add_all([User(id=110, username='Alice'), User(id=111, username='Bob')])
            db.add(TenantMember(tenant_id=1, user_id=110))
            db.commit()
            row = {'creator': 110, 'editor': '__automation__'}
            with formula_tables.scope(db, 1):
                context = dyn_engine.formula_context(fields, row)
                self.assertEqual(expr.evaluate(expr.parse('[creator].CONCAT("-", [editor])'), context), 'Alice-自动化')
                self.assertEqual(dyn_engine.formula_context(fields, {'creator': '110'})['creator'], 'Alice')
                self.assertEqual(dyn_engine.formula_context(fields, {'editor': '__ai__'})['editor'], 'AI 生成')
                self.assertEqual(dyn_engine.formula_context(fields, {'creator': 111})['creator'], '未知用户')
            self.assertEqual(row, {'creator': 110, 'editor': '__automation__'})
            self.assertIsNone(formula_tables.USER_NAME_RESOLVER.get())
        engine.dispose()
