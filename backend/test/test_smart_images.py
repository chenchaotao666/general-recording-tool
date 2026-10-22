import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import ImageFile, MetaField, MetaTable, Record
from app.services import images, json_store


class SmartImageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.setting = patch.object(images.settings, 'upload_dir', self.root)
        self.setting.start()
        self.table = MetaTable(name='images_test', label='Images', storage_mode='json')
        self.db.add(self.table)
        self.db.flush()
        self.field = MetaField(table_id=self.table.id, field_name='photo', label='Photo',
                               data_type='json', field_type='image')
        self.db.add(self.field)
        self.fid = 'a' * 32
        self.image = ImageFile(id=self.fid, size=4, mime='image/png',
                               created_at=datetime.now() - timedelta(days=2))
        self.db.add(self.image)
        self.path = images.images_dir() / self.fid
        self.path.write_bytes(b'test')
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.setting.stop()
        self.tmp.cleanup()

    def create(self):
        return json_store.create_record(self.db, self.table, [self.field], {'photo': [self.fid]})

    def test_create_copy_remove_last_reference_and_cleanup(self):
        first = self.create()
        second = self.create()
        self.assertEqual(self.image.record_id, first['id'])
        json_store.delete_record(self.db, self.table.id, first['id'], [self.field])
        self.assertEqual(self.image.record_id, second['id'])
        self.assertEqual(images.cleanup_orphans(self.db), 0)
        self.assertTrue(self.path.exists())
        json_store.update_record(self.db, self.table, [self.field], second['id'], {'photo': []})
        self.assertIsNone(self.image.record_id)
        self.assertEqual(images.cleanup_orphans(self.db), 0)
        json_store.update_record(self.db, self.table, [self.field], second['id'], {'photo': [self.fid]})
        self.assertEqual(self.image.record_id, second['id'])
        json_store.update_record(self.db, self.table, [self.field], second['id'], {'photo': []})
        self.image.created_at = datetime.now() - timedelta(days=2)
        self.db.commit()
        self.assertEqual(images.cleanup_orphans(self.db), 1)
        self.assertFalse(self.path.exists())

    def test_startup_repairs_legacy_unowned_images_before_cleanup(self):
        rec = Record(table_id=self.table.id, data={'photo': [self.fid]})
        self.db.add(rec)
        self.db.commit()
        self.assertEqual(images.cleanup_orphans(self.db), 0)
        self.assertEqual(self.image.record_id, rec.id)
        self.assertTrue(self.path.exists())

    def test_batch_rollback_preserves_ownership_and_file(self):
        rec = self.create()
        json_store.update_record(self.db, self.table, [self.field], rec['id'], {'photo': []}, commit=False)
        self.assertIsNone(self.image.record_id)
        self.db.rollback()
        self.assertEqual(self.image.record_id, rec['id'])
        self.assertEqual(self.db.get(Record, rec['id']).data['photo'], [self.fid])
        self.assertTrue(self.path.exists())

    def test_shared_reference_survives_cascade_and_removed_field_expires(self):
        rec = self.create()
        other = MetaTable(name='other', label='Other', storage_mode='json')
        self.db.add(other)
        self.db.flush()
        field = MetaField(table_id=other.id, field_name='photo', label='Photo', data_type='json', field_type='image')
        self.db.add(field)
        copy = Record(table_id=other.id, data={'photo': [self.fid]})
        self.db.add(copy)
        self.db.commit()
        self.db.delete(self.db.get(Record, rec['id']))
        images.delete_table_images(self.db, self.table.id)
        self.db.commit()
        self.assertTrue(self.path.exists())
        self.assertEqual(self.image.record_id, copy.id)
        self.db.delete(field)
        self.db.commit()
        images.cleanup_orphans(self.db)
        self.assertIsNone(self.image.record_id)


if __name__ == '__main__':
    unittest.main()
