"""隔离 SQLite 验证多企业创建、邀请、成员边界与分享，不连接工作数据库。"""
import unittest
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import EnterpriseProfile, MetaTable, TenantMember, UsageCounter, SmartDoc, SmartDocEntry, SmartPermGroup
from app.routers import auth, enterprises, members, tables, tenants, users, shares, smart_perms, smart_docs
from app.services import entitlement
from app.services.migrate import _seed_plans, _seed_rbac, _migrate_v7_tenant_ids


class EnterpriseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            _seed_plans(conn)
            _seed_rbac(conn)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        def database():
            with self.Session() as db:
                yield db
        app = FastAPI()
        for module in [auth, enterprises, members, tables, tenants, users, shares, smart_perms, smart_docs]:
            app.include_router(module.router)
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        entitlement.invalidate_cache()
        self.owner = self.register('owner')
        self.member = self.register('member')
        self.outsider = self.register('outsider')

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        entitlement.invalidate_cache()

    def register(self, name):
        r = self.client.post('/api/auth/register', json={'username': name, 'password': 'testing123'})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def headers(self, who, tid=None):
        return {'Authorization': 'Bearer ' + who['token'], 'X-Tenant-Id': str(tid or who['user']['tenant']['id'])}

    def create(self, name='First enterprise'):
        r = self.client.post('/api/enterprises', json={'name': name}, headers=self.headers(self.owner))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['tenant']['id']

    def code(self, tid):
        r = self.client.post('/api/enterprises/invitation', headers=self.headers(self.owner, tid))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['code']

    def join(self, code, who=None):
        return self.client.post('/api/enterprises/join', json={'code': code}, headers=self.headers(who or self.member))

    def test_create_and_join_multiple_enterprises(self):
        first, second = self.create(), self.create('Second enterprise')
        for tid in [first, second]:
            code = self.code(tid)
            preview = self.client.post('/api/enterprises/preview', json={'code': code}, headers=self.headers(self.member))
            self.assertEqual(preview.json()['id'], tid)
            for _ in range(2):
                r = self.join(code)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()['role'], 'user')
            with self.Session() as db:
                self.assertEqual(db.query(UsageCounter).filter_by(tenant_id=tid).one().seat_count, 2)
        mine = self.client.get('/api/tenants/mine', headers=self.headers(self.member)).json()
        self.assertEqual(len(mine), 3)
        denied = self.client.post('/api/tenants/switch', json={'tenant_id': first}, headers=self.headers(self.outsider))
        self.assertEqual(denied.status_code, 403)
        allowed = self.client.post('/api/tenants/switch', json={'tenant_id': second}, headers=self.headers(self.member))
        self.assertEqual(allowed.json()['tenant']['id'], second)

    def test_legacy_orphan_usage_does_not_block_creation(self):
        # 真实旧库形态：tenants 是可复用 rowid 的表，usage_counters 留有历史编号。
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE tenants_old (id INTEGER PRIMARY KEY, name VARCHAR(128) NOT NULL, '
                              'type VARCHAR(16), owner_user_id INTEGER, created_at DATETIME)'))
            conn.execute(text('INSERT INTO tenants_old SELECT * FROM tenants'))
            conn.execute(text('DROP TABLE tenants'))
            conn.execute(text('ALTER TABLE tenants_old RENAME TO tenants'))
            next_id = conn.execute(text('SELECT MAX(id)+1 FROM tenants')).scalar()
            conn.execute(text('INSERT INTO usage_counters(tenant_id, seat_count) VALUES (:id, 17)'), {'id': next_id})
            _migrate_v7_tenant_ids(conn)
            _migrate_v7_tenant_ids(conn)  # 重跑不降低序列、不改业务数据
        first = self.create('After legacy migration')
        self.assertGreater(first, next_id)
        with self.engine.begin() as conn:
            self.assertEqual(conn.execute(text('SELECT seat_count FROM usage_counters WHERE tenant_id=:id'), {'id': next_id}).scalar(), 17)
            conn.execute(text('DELETE FROM tenants WHERE id=:id'), {'id': first})
        second = self.create('After deletion')
        self.assertGreater(second, first)

    def test_invite_permissions_rotation_expiry_and_disabled(self):
        tid = self.create()
        old = self.code(tid)
        code = self.code(tid)
        self.assertEqual(self.join(old).status_code, 400)
        self.assertEqual(self.join(code).status_code, 200)
        self.assertEqual(self.client.post('/api/enterprises/invitation', headers=self.headers(self.member, tid)).status_code, 403)
        self.assertEqual(self.client.put('/api/enterprises/current', json={'name': 'Hijacked'}, headers=self.headers(self.member, tid)).status_code, 403)
        with self.Session() as db:
            db.query(TenantMember).filter_by(tenant_id=tid, user_id=self.member['user']['id']).one().status = 'disabled'
            db.commit()
        self.assertEqual(self.join(code).status_code, 403)
        with self.Session() as db:
            db.get(EnterpriseProfile, tid).invite_expires_at = datetime.now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.join(code, self.outsider).status_code, 400)

    def test_private_tables_and_colleague_sharing(self):
        tid = self.create()
        self.assertEqual(self.join(self.code(tid)).status_code, 200)
        with self.Session() as db:
            table = MetaTable(name='test_private', label='Private', owner_id=self.member['user']['id'], tenant_id=tid)
            db.add(table)
            db.commit()
            table_id = table.id
        self.assertEqual(self.join(self.code(tid), self.outsider).status_code, 200)
        h = self.headers(self.outsider, tid)
        self.assertEqual(self.client.get(f'/api/tables/{table_id}', headers=h).status_code, 404)
        self.assertEqual(self.client.get('/api/tables', headers=h).json(), [])
        found = self.client.get('/api/users/search?q=outsider', headers=self.headers(self.member, tid)).json()
        self.assertEqual(found[0]['id'], self.outsider['user']['id'])
        r = self.client.post(f'/api/tables/{table_id}/shares', headers=self.headers(self.member, tid), json={
            'user_id': self.outsider['user']['id'], 'can_view': True, 'can_edit': False})
        self.assertEqual(r.status_code, 200, r.text)
        share_id = r.json()['id']
        self.assertEqual(self.client.post(f'/api/shares/{share_id}/accept', headers=h).status_code, 200)
        visible = self.client.get('/api/tables', headers=h)
        self.assertEqual(visible.status_code, 200, visible.text)
        self.assertEqual(len(visible.json()), 1)
        self.assertFalse(visible.json()[0]['my_perms']['can_edit'])
        other = self.create('Other')
        self.assertEqual(self.client.get('/api/tables', headers=self.headers(self.owner, other)).json(), [])

    def test_existing_invitation_does_not_count_seat_twice(self):
        tid = self.create()
        r = self.client.post('/api/members/invite', headers=self.headers(self.owner, tid), json={'username': 'member'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.join(self.code(tid)).status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.query(UsageCounter).filter_by(tenant_id=tid).one().seat_count, 2)

    def test_invalid_name_and_readonly_enterprise(self):
        r = self.client.post('/api/enterprises', json={'name': '   '}, headers=self.headers(self.owner))
        self.assertEqual(r.status_code, 400)
        tid = self.create()
        code = self.code(tid)
        with self.Session() as db:
            entitlement.get_subscription(db, tid).status = 'expired'
            db.commit()
        self.assertEqual(self.join(code).status_code, 403)

    def test_smart_table_explicit_group_grant(self):
        tid = self.create()
        self.assertEqual(self.join(self.code(tid)).status_code, 200)
        uid = self.owner['user']['id']
        with self.Session() as db:
            table = MetaTable(name='smart_private', label='Smart', owner_id=uid, tenant_id=tid)
            doc = SmartDoc(tenant_id=tid, owner_id=uid, name='Smart', is_default=True)
            db.add_all([table, doc]); db.flush()
            entry = SmartDocEntry(doc_id=doc.id, type='sheet', name='Smart', ref_table_id=table.id)
            group = SmartPermGroup(doc_id=doc.id, name='Reviewers', member_ids=[self.member['user']['id']])
            db.add_all([entry, group]); db.commit()
            table_id, entry_id, group_id, doc_id = table.id, entry.id, group.id, doc.id
        h = self.headers(self.member, tid)
        self.assertEqual(self.client.get(f'/api/smart/docs/{doc_id}/tree', headers=h).json()['entries'], [])
        self.assertEqual(self.client.get(f'/api/smart/entries/{entry_id}/permission', headers=h).status_code, 404)
        self.assertEqual(self.client.patch(f'/api/smart/entries/{entry_id}', json={'name': 'Changed'}, headers=h).status_code, 404)
        base = self.client.get(f'/api/smart/entries/{entry_id}/permission', headers=self.headers(self.owner, tid)).json()
        self.assertEqual(base['base']['level'], 'NONE')
        r = self.client.put(f'/api/smart/perm-groups/{group_id}/grants/{entry_id}',
                            json={'profile': {'level': 'VIEW'}}, headers=self.headers(self.owner, tid))
        self.assertEqual(r.status_code, 200, r.text)
        result = self.client.get(f'/api/tables/{table_id}', headers=h)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertFalse(result.json()['my_perms']['can_edit'])
        self.assertEqual(self.client.patch(f'/api/smart/entries/{entry_id}', json={'name': 'Changed'}, headers=h).status_code, 403)
        self.assertEqual(len(self.client.get(f'/api/smart/docs/{doc_id}/tree', headers=h).json()['entries']), 1)


if __name__ == '__main__':
    unittest.main()
