"""隔离 SQLite 验证报表/工作流/记事本/画板按工作空间（个人空间/企业）隔离，不连接工作数据库。"""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import MetaTable, ReportTemplate
from app.routers import auth, enterprises, notes, reports, whiteboards, workflows
from app.services import entitlement
from app.services.migrate import _migrate_v8_workspace_data, _seed_plans, _seed_rbac


class WorkspaceIsolationTests(unittest.TestCase):
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
        for module in [auth, enterprises, notes, whiteboards, workflows, reports]:
            app.include_router(module.router)
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        entitlement.invalidate_cache()
        self.owner = self.register('owner')
        self.personal = self.owner['user']['tenant']['id']
        r = self.client.post('/api/enterprises', json={'name': 'Acme'}, headers=self.headers())
        self.assertEqual(r.status_code, 200, r.text)
        self.enterprise = r.json()['tenant']['id']

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        entitlement.invalidate_cache()

    def register(self, name):
        r = self.client.post('/api/auth/register', json={'username': name, 'password': 'testing123'})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def headers(self, tid=None):
        return {'Authorization': 'Bearer ' + self.owner['token'],
                'X-Tenant-Id': str(tid or self.personal)}

    def test_notes_scoped_per_workspace(self):
        r = self.client.post('/api/notes', json={'title': 'personal note'}, headers=self.headers())
        self.assertEqual(r.status_code, 200, r.text)
        note_id = r.json()['id']
        # 企业空间内列表为空、按 id 访问 404
        h = self.headers(self.enterprise)
        self.assertEqual(self.client.get('/api/notes/tree', headers=h).json()['notes'], [])
        self.assertEqual(self.client.get(f'/api/notes/{note_id}', headers=h).status_code, 404)
        self.assertEqual(self.client.put(f'/api/notes/{note_id}', json={'title': 'x'}, headers=h).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/notes/{note_id}', headers=h).status_code, 404)
        # 企业空间内新建互不影响；个人空间仍只有自己的一条
        r2 = self.client.post('/api/notes', json={'title': 'corp note'}, headers=h)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertNotEqual(r2.json()['id'], note_id)
        mine = self.client.get('/api/notes/tree', headers=self.headers()).json()['notes']
        self.assertEqual([n['title'] for n in mine], ['personal note'])
        corp = self.client.get('/api/notes/tree', headers=h).json()['notes']
        self.assertEqual([n['title'] for n in corp], ['corp note'])
        # 企业空间不能挂到个人空间的父页面下
        r3 = self.client.post('/api/notes', json={'title': 'child', 'parent_id': note_id}, headers=h)
        self.assertEqual(r3.status_code, 404)

    def test_whiteboards_scoped_per_workspace(self):
        r = self.client.post('/api/whiteboards', json={'title': 'personal board'}, headers=self.headers())
        self.assertEqual(r.status_code, 200, r.text)
        wb_id = r.json()['id']
        h = self.headers(self.enterprise)
        self.assertEqual(self.client.get('/api/whiteboards/tree', headers=h).json()['whiteboards'], [])
        self.assertEqual(self.client.get(f'/api/whiteboards/{wb_id}', headers=h).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/whiteboards/{wb_id}', headers=h).status_code, 404)
        mine = self.client.get('/api/whiteboards/tree', headers=self.headers()).json()['whiteboards']
        self.assertEqual(len(mine), 1)

    def test_workflows_scoped_per_workspace(self):
        r = self.client.post('/api/workflows', headers=self.headers(),
                             json={'name': 'personal wf', 'draft': True, 'trigger': {'type': 'manual'},
                                   'nodes': [], 'edges': []})
        self.assertEqual(r.status_code, 200, r.text)
        wf_id = r.json()['id']
        h = self.headers(self.enterprise)
        self.assertEqual(self.client.get('/api/workflows', headers=h).json(), [])
        self.assertEqual(self.client.get(f'/api/workflows/{wf_id}', headers=h).status_code, 404)
        self.assertEqual(self.client.post(f'/api/workflows/{wf_id}/toggle', headers=h).status_code, 404)
        r2 = self.client.post('/api/workflows', headers=h,
                              json={'name': 'corp wf', 'draft': True, 'trigger': {'type': 'manual'},
                                    'nodes': [], 'edges': []})
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertEqual([w['name'] for w in self.client.get('/api/workflows', headers=self.headers()).json()],
                         ['personal wf'])
        self.assertEqual([w['name'] for w in self.client.get('/api/workflows', headers=h).json()], ['corp wf'])

    def test_reports_scoped_per_workspace(self):
        uid = self.owner['user']['id']
        with self.Session() as db:
            t = MetaTable(name='rep_table', label='Rep', owner_id=uid, tenant_id=self.personal)
            db.add(t)
            db.flush()
            db.add(ReportTemplate(name='personal report', table_id=t.id, user_id=uid, tenant_id=self.personal))
            db.add(ReportTemplate(name='corp report', table_id=t.id, user_id=uid, tenant_id=self.enterprise))
            db.commit()
            ids = {r.name: r.id for r in db.query(ReportTemplate).all()}
        mine = self.client.get('/api/reports', headers=self.headers()).json()
        self.assertEqual([t['name'] for t in mine], ['personal report'])
        corp = self.client.get('/api/reports', headers=self.headers(self.enterprise)).json()
        self.assertEqual([t['name'] for t in corp], ['corp report'])
        # 跨空间按 id 访问 404
        h = self.headers(self.enterprise)
        self.assertEqual(self.client.get(f"/api/reports/{ids['personal report']}", headers=h).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/reports/{ids['personal report']}", headers=h).status_code, 404)

    def test_v8_backfills_notes_and_whiteboards_to_personal_tenant(self):
        uid = self.owner['user']['id']
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO notes (user_id, title) VALUES (:u, 'legacy note')"), {'u': uid})
            conn.execute(text("INSERT INTO whiteboards (user_id, title) VALUES (:u, 'legacy board')"), {'u': uid})
            _migrate_v8_workspace_data(conn)
            _migrate_v8_workspace_data(conn)  # 幂等：重跑不改动已回填数据
            note_tid = conn.execute(text("SELECT tenant_id FROM notes WHERE title='legacy note'")).scalar()
            wb_tid = conn.execute(text("SELECT tenant_id FROM whiteboards WHERE title='legacy board'")).scalar()
        self.assertEqual(note_tid, self.personal)
        self.assertEqual(wb_tid, self.personal)


if __name__ == '__main__':
    unittest.main()
