import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from fastapi import HTTPException
from app.routers import images


class ImageMetadataTests(unittest.TestCase):
    def setUp(self):
        self.row = SimpleNamespace(id='a' * 32, filename='photo.png', size=5, mime='image/png',
                                   uploader_id=1, table_id=None, note_id=None)
        self.ctx = SimpleNamespace(user=SimpleNamespace(id=1), tenant=SimpleNamespace(id=1))
        self.db = Mock()

    def test_rename_persists_and_rejects_empty_or_path_names(self):
        with patch.object(images.images, 'get_image', return_value=(self.row, '/unused')):
            result = images.rename_image(self.row.id, images.ImageName(filename='new.png'), self.db, self.ctx)
            self.assertEqual(result['filename'], 'new.png')
            self.db.commit.assert_called_once()
            for name in (' ', '../image.png', 'a\\b.png', 'new.jpg', 'new', '.png'):
                with self.assertRaises(HTTPException):
                    images.rename_image(self.row.id, images.ImageName(filename=name), self.db, self.ctx)

    def test_nonowner_cannot_read_unbound_image_and_viewer_cannot_rename(self):
        with patch.object(images.images, 'get_image', return_value=(self.row, '/unused')):
            self.ctx.user.id = 2
            with self.assertRaises(HTTPException):
                images.image_meta(self.row.id, self.db, self.ctx)
            self.row.table_id = 3
            with patch.object(images, 'get_table_access', return_value=SimpleNamespace(can_edit=False)):
                with self.assertRaises(HTTPException) as caught:
                    images.rename_image(self.row.id, images.ImageName(filename='new.png'), self.db, self.ctx)
                self.assertEqual(caught.exception.status_code, 403)
            self.db.commit.assert_not_called()
