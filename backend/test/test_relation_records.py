import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from app.routers import smart_records as api


class RelationRecordsTests(unittest.TestCase):
    def query(self, **params):
        fields = [SimpleNamespace(id=i, field_name=n, label=n, field_type='text', options={})
                  for i, n in enumerate(['title', 'secret'])]
        eff = Mock(can_add_record=False, can_edit=False)
        eff.field_rights_map.return_value = {'title': {'view': True}, 'secret': {'view': False}}
        eff.row_viewable.side_effect = lambda r, _: r['id'] != 2
        eff.row_editable.return_value = False
        eff.to_client.return_value = {}
        access = SimpleNamespace(table=SimpleNamespace(label='Target'), can_edit=False, ctx=SimpleNamespace(user=SimpleNamespace(id=1)))
        rows = [{'id': i, 'title': f'Record {i}', 'secret': 'hidden'} for i in range(1, 205)]
        with patch.object(api, '_load_effective_view', return_value=(None, {})), patch.object(api, 'get_meta_fields', return_value=fields), patch.object(api, '_effective', return_value=eff), patch.object(api.json_store, 'all_dicts', return_value=rows), patch.object(api, '_inject_system_and_lookup'):
            return api.relation_records(1, db=None, access=access, **params)

    def test_pagination_and_projection(self):
        result = self.query(page=5, page_size=50)
        self.assertEqual(result['total'], 203)
        self.assertEqual(len(result['items']), 3)
        self.assertNotIn('secret', result['items'][0])
        self.assertTrue(result['items'][0]['__readonly'])

    def test_selected_ids_still_enforce_permissions(self):
        result = self.query(ids='2,204')
        self.assertEqual([r['id'] for r in result['items']], [204])

    def test_search_does_not_expose_hidden_fields(self):
        self.assertEqual(self.query(search='hidden')['total'], 0)
        self.assertEqual(self.query(search='Record 204')['items'][0]['id'], 204)
