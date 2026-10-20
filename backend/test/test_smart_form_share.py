import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import MetaTable, MetaView, SharedLink
from app.routers import smart_forms as api
from app.utils.auth import verify_password


class FormShareTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        table = MetaTable(name="share_test", label="Share", storage_mode="json")
        self.db.add(table)
        self.db.flush()
        self.view = MetaView(table_id=table.id, name="Form", type="form", config={})
        self.db.add(self.view)
        self.db.commit()
        self.ctx = SimpleNamespace(user=SimpleNamespace(id=1))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def save(self, payload):
        with patch.object(api, "_require_form_manager"):
            return api.create_share_link(self.view.id, payload, self.db, self.ctx)["link"]

    def test_password_partial_update_and_public_access(self):
        initial = self.save({"password": "test-pass", "expires_in_days": 7})
        token = initial["token"]
        with self.assertRaises(HTTPException) as error:
            api._public_view(self.db, token, None)
        self.assertEqual(error.exception.detail["code"], "password_required")
        self.assertEqual(api._public_view(self.db, token, "test-pass").id, self.view.id)
        unchanged = self.save({})
        self.assertTrue(unchanged["has_password"])
        self.assertEqual(unchanged["expires_at"], initial["expires_at"])
        changed = self.save({"password": "new-pass"})
        self.assertEqual(changed["token"], token)
        self.assertEqual(changed["expires_at"], initial["expires_at"])
        row = self.db.query(SharedLink).one()
        self.assertTrue(verify_password("new-pass", row.password_hash))
        with self.assertRaises(HTTPException):
            api._public_view(self.db, token, "test-pass")
        self.save({"password": ""})
        self.assertEqual(api._public_view(self.db, token, None).id, self.view.id)
        row.expires_at = datetime.now() - timedelta(days=1)
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            api._public_view(self.db, token, None)
        self.assertEqual(error.exception.status_code, 410)

    def test_reject_short_password_and_close_link(self):
        self.save({"password": "original"})
        with self.assertRaises(HTTPException):
            self.save({"password": "abc"})
        row = self.db.query(SharedLink).one()
        self.assertTrue(verify_password("original", row.password_hash))
        token = row.token
        with patch.object(api, "_require_form_manager"):
            api.delete_share_link(self.view.id, self.db, self.ctx)
        with self.assertRaises(HTTPException) as error:
            api._public_view(self.db, token, "original")
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
