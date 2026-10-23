import unittest
from copy import deepcopy

from test.llm.whiteboard.eval_whiteboard import apply_context, validate, HERE
from test.llm.whiteboard.whiteboard_cases import CASES, SCENE


class WhiteboardEvalTests(unittest.TestCase):
    def test_catalog_has_50_unique_cases_and_assets(self):
        self.assertEqual(len(CASES), 50)
        self.assertEqual(len({c['id'] for c in CASES}), 50)
        self.assertEqual(sum(len(c['turns']) for c in CASES), 58)
        for c in CASES:
            self.assertTrue(c['visual_review'])
            for turn in c['turns']:
                self.assertIn('mode', turn['expect'])
                if turn.get('image'):
                    self.assertTrue((HERE / 'whiteboard_fixtures' / turn['image']).is_file())

    def test_validator_detects_wrong_color_extra_edit_and_bad_mode(self):
        expected = CASES[10]['turns'][0]['expect']
        valid = {'mode': 'modify', 'edits': [{'id': 'start', 'backgroundColor': '#ff0000', 'fillStyle': 'solid'}]}
        validate(valid, expected, SCENE)
        wrong_color = deepcopy(valid)
        wrong_color['edits'][0]['backgroundColor'] = '#00ff00'
        wrong_property = deepcopy(valid)
        wrong_property['edits'][0]['strokeColor'] = '#0000ff'
        for invalid in [wrong_color, wrong_property, {**valid, 'mode': 'replace'}]:
            with self.assertRaises(AssertionError):
                validate(invalid, expected, SCENE)
        unchanged_property = deepcopy(valid)
        unchanged_property['edits'][0]['strokeColor'] = '#000000'
        validate(unchanged_property, expected, SCENE)

    def test_previous_turn_changes_feed_next_turn_without_mutating_fixture(self):
        context = apply_context(SCENE, {'mode': 'modify', 'edits': [{'id': 'start', 'text': '申请提交'}]}, 1)
        self.assertEqual(context[0]['text'], '申请提交')
        self.assertEqual(SCENE[0]['text'], '开始')
        deleted = apply_context(context, {'mode': 'modify', 'edits': [{'id': 'start', 'delete': True}]}, 2)
        self.assertEqual([c['id'] for c in deleted], ['end', 'edge'])
        self.assertNotIn('fromId', deleted[1])

    def test_source_selection_cannot_be_bypassed(self):
        with self.assertRaises(AssertionError):
            apply_context([{**c, 'selected': c['id'] == 'start'} for c in SCENE],
                          {'mode': 'modify', 'edits': [{'id': 'end', 'delete': True}]}, 1)

    def test_connection_direction_and_summary_checks(self):
        expected = {'mode': 'replace', 'connections': [['A', 'B']]}
        result = {'mode': 'replace', 'nodes': [{'id': 'a', 'label': 'A'}, {'id': 'b', 'label': 'B'}], 'edges': [{'source': 'b', 'target': 'a'}]}
        with self.assertRaises(AssertionError):
            validate(result, expected, [])
        with self.assertRaises(AssertionError):
            validate({'mode': 'summarize', 'summary': '开始和结束'}, {'mode': 'summarize', 'summary_excludes': ['结束']}, [])


if __name__ == '__main__':
    unittest.main()
