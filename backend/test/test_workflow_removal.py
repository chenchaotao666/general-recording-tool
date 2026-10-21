"""下线迁移只清理工作流数据，并兼容新库与重复执行。"""
import json
import unittest

from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app import models
from app.services.migrate import _migrate_v9_remove_workflows


class WorkflowRemovalTests(unittest.TestCase):
    def test_legacy_cleanup_preserves_other_features(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text('PRAGMA foreign_keys=ON'))
            conn.execute(text('CREATE TABLE workflows (id INTEGER PRIMARY KEY)'))
            conn.execute(text('CREATE TABLE workflow_runs (id INTEGER PRIMARY KEY, workflow_id INTEGER REFERENCES workflows(id))'))
            for table in ('workflow_jobs', 'workflow_node_runs'):
                conn.execute(text(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES workflow_runs(id))'))
            conn.execute(text('INSERT INTO workflows VALUES (1)'))
            conn.execute(text('INSERT INTO workflow_runs VALUES (1, 1)'))
            for table in ('workflow_jobs', 'workflow_node_runs'):
                conn.execute(text(f'INSERT INTO {table} VALUES (1, 1)'))
            conn.execute(text("INSERT INTO permissions (id, code, name) VALUES (1, 'menu_workflows', 'legacy'), (2, 'menu_reports', 'reports')"))
            conn.execute(text("INSERT INTO roles (id, code, name) VALUES (1, 'user', 'user')"))
            conn.execute(text('INSERT INTO role_permissions (role_id, permission_id) VALUES (1, 1), (1, 2)'))
            conn.execute(text("INSERT INTO app_settings (key, value) VALUES ('mcp_tokens', '{}'), ('smtp', '{}')"))
            conn.execute(text("INSERT INTO notifications (id, link) VALUES (1, '/workflows/runs/1'), (2, '/approve/token'), (3, '/smart/table/1')"))
            cards = [{'type': 'todos'}, {'type': 'menu', 'config': {'path': '/workflows'}}, {'type': 'notifications'}]
            layout = {'sections': [{'cards': cards, 'groups': [{'cards': cards}]}]}
            conn.execute(text('INSERT INTO home_default_layout (id, layout_json) VALUES (1, :layout)'), {'layout': json.dumps(layout)})
            _migrate_v9_remove_workflows(conn)
            _migrate_v9_remove_workflows(conn)
            self.assertFalse(any(name.startswith('workflow') for name in inspect(conn).get_table_names()))
            self.assertEqual(conn.execute(text('SELECT code FROM permissions')).scalars().all(), ['menu_reports'])
            self.assertEqual(conn.execute(text('SELECT permission_id FROM role_permissions')).scalars().all(), [2])
            self.assertEqual(conn.execute(text('SELECT key FROM app_settings')).scalars().all(), ['smtp'])
            self.assertEqual(conn.execute(text('SELECT id FROM notifications')).scalars().all(), [3])
            updated = json.loads(conn.execute(text('SELECT layout_json FROM home_default_layout')).scalar_one())
            section = updated['sections'][0]
            self.assertEqual(section['cards'], [{'type': 'notifications'}])
            self.assertEqual(section['groups'][0]['cards'], [{'type': 'notifications'}])
            self.assertIn('report_templates', inspect(conn).get_table_names())
        engine.dispose()

    def test_fresh_schema_and_public_routes(self):
        from app.main import app
        from app.services.llm.prompts import build_analyze_prompt, build_report_prompt, build_assistant_prompt
        from app.services.template_data import _remap

        self.assertFalse(any(name.startswith('workflow') for name in Base.metadata.tables))
        for path in app.openapi()['paths']:
            self.assertFalse(any(part in path for part in ('/workflows', '/workflow-templates', '/mcp', '/approve')))
        prompt = build_assistant_prompt('hello', [], [], None, '2026-10-21')
        self.assertNotIn('workflow', prompt)
        for action in ('web_search', 'fill_records', 'create_table', 'query', 'gen_excel', 'create_report', 'alter_table'):
            self.assertIn(action, prompt)
        self.assertTrue(build_analyze_prompt([], []))
        self.assertTrue(build_report_prompt('report', []))
        self.assertEqual(_remap({'table_id': '$sales'}, {'sales': 3}), {'table_id': 3})


if __name__ == '__main__':
    unittest.main()
