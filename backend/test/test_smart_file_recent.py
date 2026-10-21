import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.services import smart_files


class RecentFilesTests(unittest.TestCase):
    def test_recent_only_lists_current_users_files_in_current_table(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(smart_files, '_root', return_value=Path(folder)):
            mine = smart_files.save(b'mine', 'mine.txt', 1, 2)
            smart_files.save(b'other user', 'other.txt', 1, 3)
            smart_files.save(b'other table', 'another.txt', 2, 2)
            self.assertEqual(smart_files.recent(1, 2), [mine])
            self.assertEqual(smart_files.recent(3, 2), [])
