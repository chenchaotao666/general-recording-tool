import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import ai_field_service as service
from app.services.field_registry import validate_field_type_config


class AiOutputTypesTests(unittest.TestCase):
    def test_supported_types_can_be_saved_and_configured(self):
        source = SimpleNamespace(field_name='source', label='Source', field_type='text')
        for kind in ('percent', 'progress', 'date'):
            with self.subTest(kind=kind):
                validate_field_type_config('ai', {'outputType': kind, 'systemPrompt': 'Process input'})
                with patch.object(service, 'get_meta_fields', return_value=[source]), \
                     patch.object(service, '_quota_ok', return_value=True), \
                     patch.object(service, '_llm_config', return_value={}), \
                     patch.object(service, 'preview_rows', return_value=[]), \
                     patch.object(service, 'quota_status', return_value={}):
                    result = service.configure(None, SimpleNamespace(id=1, tenant_id=None), {
                        'scene': 'custom', 'input_fields': ['source'], 'output_type': kind,
                    })
                self.assertEqual(result['config']['outputType'], kind)
                system, _ = service.build_prompt_cfg(None, {'outputType': kind, 'systemPrompt': 'Process'}, [], {}, [])
                self.assertIn(service.OUTPUT_RULES[kind], system)

    def test_instruction_generation_can_skip_preview(self):
        source = SimpleNamespace(field_name='source', label='Source', field_type='text')
        with patch.object(service, 'get_meta_fields', return_value=[source]), \
             patch.object(service, '_quota_ok', return_value=True), \
             patch.object(service, '_llm_config', return_value={'outputType': 'number', 'prompt': 'Count items'}), \
             patch.object(service, 'preview_rows', return_value=[]) as preview, \
             patch.object(service, 'quota_status', return_value={}):
            result = service.configure(None, SimpleNamespace(id=1, tenant_id=None), {
                'scene': 'custom', 'input_fields': ['source'], 'include_preview': False,
            })
            preview.assert_not_called()
            self.assertEqual(result['config']['outputType'], 'number')
            self.assertEqual(result['config']['systemPrompt'], 'Count items')
            self.assertEqual(result['preview'], [])

    def test_percent_and_progress_conversion(self):
        for kind in ('percent', 'progress'):
            self.assertEqual(service.coerce_basic(kind, '25%'), 25)
            self.assertEqual(service.coerce_basic(kind, 0.25), 0.25)
            self.assertIsNone(service.coerce_basic(kind, True))
            self.assertIsNone(service.coerce_basic(kind, 'unknown'))
            self.assertIsNone(service.coerce_basic(kind, float('inf')))
        self.assertEqual(service.coerce_basic('percent', '125%'), 125)
        self.assertEqual(service.coerce_basic('progress', 100), 100)
        self.assertIsNone(service.coerce_basic('progress', 101))
        self.assertIsNone(service.coerce_basic('progress', -1))

    def test_dates_are_normalized_and_invalid_dates_are_empty(self):
        for raw in ('2026-10-23', '2026/10/23', '2026-10-23T12:00:00Z'):
            self.assertEqual(service.coerce_basic('date', raw), '2026-10-23')
        for raw in ('2026-02-30', 'unknown', 20261023, True, None):
            self.assertIsNone(service.coerce_basic('date', raw))


if __name__ == '__main__':
    unittest.main()
