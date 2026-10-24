import json
import tempfile
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from zipfile import ZipFile

from PIL import Image
from app.services import ai_field_service as service, smart_files
from app.services.ai_scenes import SCENES, SCENE_BY_KEY
from app.services.ai_template_compute import compute, scalar
from app.services.ai_template_files import transform
from app.services.ai_local import _unix, _from_unix, luhn_ok


def field(name, kind='text', **kw):
    return NS(field_name=name, label=name, field_type=kind, table_id=7, options={}, **kw)


class TemplateComputeTests(unittest.TestCase):
    def test_catalog_has_introductions_and_consistent_execution(self):
        self.assertEqual(len(SCENES), len({s['key'] for s in SCENES}))
        for s in service.scene_catalog()['scenes']:
            with self.subTest(scene=s['key']):
                self.assertTrue(s['desc'] and s['inputHint'] and s['notes'] and s['executionLabel'])
                if s.get('local'):
                    self.assertTrue(s.get('formulaDisplay') or s.get('calculationLogic'), s['key'])
                if s.get('disabled'):
                    self.assertTrue(s.get('disabledReason'))
                if s.get('asset'):
                    self.assertTrue(s['local'])
                    self.assertEqual(s['outputType'], 'file')

    def test_role_mapping_ignores_selection_order_and_rejects_missing_roles(self):
        cfg = {'scene': 'cvBmi', 'inputFields': ['weight', 'height'], 'inputBindings': {'height': 'height', 'weight': 'weight'}}
        fs = [field('weight', 'number'), field('height', 'number')]
        service.validate_template_config(cfg, fs)
        raw, billable, tokens = service.compute_raw(None, cfg, fs, {'weight': 70, 'height': 175}, [])
        self.assertEqual((raw, billable, tokens), (22.9, False, 0))
        cfg['inputBindings']['height'] = ''
        with self.assertRaisesRegex(ValueError, '身高'):
            service.validate_template_config(cfg, fs)

    def test_calendar_dates_numbers_and_invalid_values(self):
        self.assertEqual(compute('workdays', {'inputFields': ['a', 'b']}, {'a': '2026-10-12', 'b': '2026-10-16'}, None), 5)
        self.assertEqual(compute('hrAge', {'inputFields': ['a']}, {'a': '2000-10-25'}, None, date(2026, 10, 24)), 25)
        self.assertEqual(compute('stHealthExpiry', {'inputFields': ['a']}, {'a': '2024-02-29'}, None), '2025-02-28')
        self.assertEqual(compute('pdStock', {'inputFields': ['a', 'b', 'c']}, {'a': 100, 'b': 20, 'c': 15}, None), 105)
        self.assertEqual(compute('pdDefect', {'inputFields': ['a', 'b']}, {'a': 3, 'b': 200}, None), 1.5)
        with self.assertRaisesRegex(ValueError, '分母'):
            compute('pdDefect', {'inputFields': ['a', 'b']}, {'a': 1, 'b': 0}, None)
        with self.assertRaisesRegex(ValueError, '不能早于'):
            compute('stHours', {'inputFields': ['a', 'b']}, {'a': '2026-01-02', 'b': '2026-01-01'}, None)

    def test_aggregate_uses_whole_table_and_select_labels(self):
        cfg = {'scene': 'taskCompletion', 'inputFields': ['p', 'status']}
        fs = [field('p'), field('status', 'singleSelect')]
        fs[1].options = {'options': [{'id': 'done', 'label': '已完成'}, {'id': 'todo', 'label': '未开始'}]}
        rows = [{'p': 'A', 'status': 'done'}, {'p': 'A', 'status': 'todo'}, {'p': 'B', 'status': 'done'}]
        self.assertEqual(service.compute_raw(None, cfg, fs, rows[0], [], rows)[0], 50)
        self.assertEqual(compute('mkRank', {'inputFields': ['n']}, {'n': 5}, [{'n': 10}, {'n': 5}, {'n': 5}, {'n': None}]), 2)
        self.assertEqual(compute('memberWorkload', {'inputFields': ['p', 'v']}, {'p': 'A'}, [{'p': 'A', 'v': 3}, {'p': 'A', 'v': 5}, {'p': 'B', 'v': 99}]), 8)

    def test_local_extract_and_timezone_are_deterministic(self):
        self.assertEqual(scalar('exEmail', 'a@example.com a@example.com'), 'a@example.com')
        self.assertEqual(scalar('exJson', '{"user":{"name":"张三"},"n":[1,2]}'), 'user.name: 张三\nn[0]: 1\nn[1]: 2')
        self.assertEqual(scalar('exDate', '于2026年3月20日启动'), '2026-03-20')
        self.assertEqual(scalar('cvPinyin', '张三'), 'zhangsan')
        self.assertEqual(scalar('hrGender', '11010519491231002X'), '女')
        self.assertIsNone(scalar('hrGender', '张三'))
        self.assertFalse(luhn_ok('abc4532015112830366'))
        self.assertFalse(luhn_ok('0000000000000000'))
        self.assertEqual(_unix('1970-01-01 08:00:00'), 0)
        self.assertEqual(_from_unix(0), '1970-01-01 08:00:00')

    def test_missing_optional_role_does_not_fall_back_to_another_field(self):
        cfg = {'inputFields': ['start', 'done'], 'inputBindings': {'start': 'start', 'done': 'done'}}
        self.assertEqual(compute('taskStatus', cfg, {'start': '2026-01-01', 'done': None}, None, date(2026, 2, 1)), '进行中')

    def test_duplicate_phone_normalization(self):
        cfg = {'scene': 'duplicatePhone', 'inputFields': ['phone']}
        fs = [field('phone')]
        rows = [{'phone': '+86 138-0000-0001'}, {'phone': '13800000001'}]
        self.assertTrue(service.compute_raw(None, cfg, fs, rows[0], [], rows)[0])
        self.assertFalse(service.compute_raw(None, cfg, fs, {'phone': ''}, [], rows)[0])

    def test_model_text_template_with_screenshot_uses_vision(self):
        provider = Mock(last_usage={})
        provider.recognize.return_value = '{"value": 12000}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.png'
            Image.new('RGB', (20, 20), 'white').save(path)
            with patch('app.services.ai_template_files.source_files', return_value=[(path, 'image.png')]), patch('app.services.llm.get_default_provider', return_value=provider):
                raw = service.compute_raw(None, {'scene': 'mkLikes', 'inputFields': ['pic']}, [field('pic', 'image')], {'pic': ['id']}, [])
        self.assertEqual(raw[0], 12000)
        provider.recognize.assert_called_once()
        provider.complete.assert_not_called()

    def test_delete_refreshes_only_table_templates(self):
        fields = [NS(field_type='ai', field_name='rank', options={'scene': 'mkRank', 'autoUpdate': True}), NS(field_type='ai', field_name='summary', options={'scene': 'summary'})]
        db = Mock(); db.query.return_value.filter_by.return_value.all.return_value = [NS(id=1), NS(id=2)]
        with patch.object(service, 'get_meta_fields', return_value=fields), patch.object(service, 'enqueue') as enqueue:
            service.handle_event(db, {'type': 'recordDeleted', 'table_id': 7})
        enqueue.assert_called_once_with(db, 7, 'rank', [1, 2], preserve_editor=True)


class TemplateFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(smart_files, '_root', return_value=self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def test_docx_and_text_extract(self):
        data = BytesIO()
        with ZipFile(data, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>合同到期：2026-12-31</w:t></w:r></w:p></w:body></w:document>')
        item = smart_files.save(data.getvalue(), 'contract.docx', 7, None)
        self.assertEqual(smart_files.document_text(item['id']), '合同到期：2026-12-31')
        item = smart_files.save('简历内容'.encode('utf-8'), 'resume.txt', 7, None)
        self.assertEqual(smart_files.document_text(item['id']), '简历内容')

    def test_qr_and_image_transforms_produce_downloadable_files(self):
        fields = [field('source')]
        output = transform(None, 'qrcode', {'inputFields': ['source']}, fields, {'source': 'https://example.com'})
        path, meta = smart_files.locate(output[0]['id'])
        self.assertEqual(meta['table_id'], 7)
        with Image.open(path) as image:
            self.assertEqual(image.format, 'PNG')
        data = BytesIO(); Image.new('RGB', (200, 100), 'white').save(data, format='PNG')
        item = smart_files.save(data.getvalue(), 'image.png', 7, None)
        fields = [field('pic', 'file')]
        for key in ('imSharpen', 'imWatermarkAdd', 'fiImagePdf'):
            output = transform(None, key, {'inputFields': ['pic']}, fields, {'pic': [item]})
            path, _ = smart_files.locate(output[0]['id'])
            self.assertTrue(path.stat().st_size > 0)
        self.assertEqual(smart_files.locate(item['id'])[0].read_bytes(), data.getvalue())

    def test_pdf_render_and_watermark(self):
        from reportlab.pdfgen import canvas
        from pypdf import PdfReader
        data = BytesIO(); c = canvas.Canvas(data); c.drawString(50, 700, 'Invoice 123'); c.save()
        item = smart_files.save(data.getvalue(), 'invoice.pdf', 7, None)
        fields = [field('pdf', 'file')]
        self.assertIn('Invoice 123', smart_files.document_text(item['id']))
        for key in ('fiPdfImage', 'fiPdfWatermark'):
            output = transform(None, key, {'inputFields': ['pdf']}, fields, {'pdf': [item]})
            path, _ = smart_files.locate(output[0]['id'])
            if key == 'fiPdfImage':
                with Image.open(path) as image:
                    self.assertEqual(image.format, 'PNG')
            else:
                self.assertEqual(len(PdfReader(path).pages), 1)

    def test_foreign_attachment_is_rejected(self):
        item = smart_files.save(b'hello', 'private.txt', 99, None)
        with self.assertRaisesRegex(ValueError, '不属于当前表'):
            service.compute_raw(None, {'scene': 'fiResume', 'inputFields': ['file']}, [field('file', 'file')], {'file': [item]}, [])


if __name__ == '__main__':
    unittest.main()
