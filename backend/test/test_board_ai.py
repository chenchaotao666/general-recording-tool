import json
import unittest
from unittest.mock import Mock, patch

from app.services.llm import gateway
from app.services.llm.board_rules import clean_edits, clean_style, resolve_mode, clean_attachment, expansion_targets
from app.services.llm.prompts import _format_board_context, build_board_prompt

CTX = [{'id': 'box1', 'type': 'rectangle', 'text': '开始', 'selected': True,
        'x': 10, 'y': 20, 'width': 100, 'height': 60, 'strokeColor': '#123456'},
       {'id': 'box2', 'type': 'ellipse', 'text': '结束'}]


class BoardAITests(unittest.TestCase):
    def test_combined_text_style_keeps_all_requested_attributes(self):
        prompt = '选中节点，文字大号，左对齐，顶部对齐，漫画风格'
        self.assertEqual(resolve_mode(prompt, CTX), 'modify')
        result = clean_edits({'edits': [{'id': 'box1', 'fontSize': 24}]}, CTX, prompt)
        self.assertEqual(result['edits'], [{'id': 'box1', 'fontSize': 28, 'textAlign': 'left', 'verticalAlign': 'top', 'roughness': 2}])
        self.assertEqual(clean_style({'fontFamily': 99, 'textAlign': 'invalid', 'verticalAlign': 'top'}), {'verticalAlign': 'top'})

    def test_fill_pattern_cannot_disappear_or_change_outline(self):
        context = [{**CTX[0], 'backgroundColor': '#ffeeaa', 'fillStyle': 'solid', 'strokeStyle': 'solid'}]
        result = clean_edits({'edits': [{'id': 'box1', 'fillStyle': 'hachure', 'backgroundColor': 'transparent', 'strokeStyle': 'dashed'}]}, context, '选中节点填充线条')
        self.assertEqual(result['edits'], [{'id': 'box1', 'fillStyle': 'hachure', 'backgroundColor': '#ffeeaa'}])
        context[0]['backgroundColor'] = 'transparent'
        result = clean_edits({'edits': [{'id': 'box1', 'fillStyle': 'hachure'}]}, context, '选中节点改成线条填充')
        self.assertEqual(result['edits'][0]['backgroundColor'], '#123456')

    def test_fill_color_keeps_hatching_and_cancel_only_clears_fill(self):
        context = [{**CTX[0], 'backgroundColor': '#ffeeaa', 'fillStyle': 'hachure'}]
        result = clean_edits({'edits': [{'id': 'box1', 'backgroundColor': '#ff0000', 'fillStyle': 'solid'}]}, context, '选中节点填充红色')
        self.assertEqual(result['edits'][0]['fillStyle'], 'hachure')
        result = clean_edits({'edits': [{'id': 'box1', 'backgroundColor': '#ffffff', 'fillStyle': 'solid'}]}, context, '取消填充')
        self.assertEqual(result['edits'], [{'id': 'box1', 'backgroundColor': 'transparent'}])

    def test_selected_style_rejects_redrawing_and_retries_as_patch(self):
        provider = Mock()
        provider.complete.side_effect = [json.dumps({'mode': 'replace', 'nodes': [{'id': 'new', 'label': '开始'}]}),
            json.dumps({'mode': 'modify', 'edits': [{'id': 'box1', 'strokeStyle': 'dashed'}]})]
        with patch.object(gateway, 'get_default_provider', return_value=provider):
            result = gateway.generate_board_content(None, '选中节点线条改成虚线', context=CTX)
        self.assertEqual(result['mode'], 'modify')
        self.assertEqual(result['edits'], [{'id': 'box1', 'strokeStyle': 'dashed'}])
        self.assertEqual(provider.complete.call_count, 2)

    def test_drawing_uses_shapes_without_extra_planning_or_review(self):
        provider = Mock()
        provider.complete.return_value = json.dumps({'type': 'drawing', 'elements': [
            {'type': 'ellipse', 'x': 0, 'y': 0, 'width': 100, 'height': 120}]})
        with patch.object(gateway, 'get_default_provider', return_value=provider):
            result = gateway.generate_board_content(None, '画一个很逼真的美女')
        self.assertEqual(provider.complete.call_count, 1)
        provider.recognize.assert_not_called()
        self.assertNotIn('visualReviewRequested', result)
        prompt = provider.complete.call_args.args[0]
        self.assertIn('优先用基础图形', prompt)
        self.assertNotIn('曲线示例', prompt)

    def test_curve_drawing_retains_closed_contour_and_budget(self):
        curve = {'type': 'curve', 'x': 0, 'y': 0, 'points': [[0, 0], [40, -20], [80, 0]],
                 'closed': True, 'backgroundColor': '#ffeeaa'}
        result = gateway._clean_drawing({'elements': [curve] * 80})
        self.assertEqual(len(result['elements']), 80)
        self.assertTrue(result['elements'][0]['closed'])
        self.assertEqual(result['elements'][0]['roughness'], 0)
        with self.assertRaises(ValueError):
            gateway._clean_drawing({'elements': [curve] * 181})

    def test_expand_whole_layer_without_repeating_existing_nodes(self):
        context = [{'id': 'root', 'type': 'rectangle', 'text': '主题'},
                   {'id': 'middle', 'type': 'rectangle', 'text': '分类'},
                   {'id': 'edge', 'fromId': 'root', 'toId': 'middle'}]
        for i in range(5):
            context.extend([{'id': f'leaf{i}', 'type': 'rectangle', 'text': f'技术{i}'},
                            {'id': f'e{i}', 'fromId': 'middle', 'toId': f'leaf{i}'}])
        prompt = '基于第三层节点继续展开分析'
        self.assertEqual(expansion_targets(prompt, context), [f'leaf{i}' for i in range(5)])
        data = {'parts': [{'type': 'diagram', 'attachTo': f'leaf{i}',
                          'nodes': [{'id': 'child', 'label': f'具体细节{i}'}], 'edges': []} for i in range(5)]}
        result = gateway._clean_content(data)
        result['mode'] = 'append'
        clean_attachment(data, result, context, prompt)
        self.assertEqual([p['attachTo'] for p in result['parts']], [f'leaf{i}' for i in range(5)])
        with self.assertRaises(ValueError):
            clean_attachment({'parts': data['parts'][:1]}, {'mode': 'append', 'parts': result['parts'][:1]}, context, prompt)
        with self.assertRaises(ValueError):
            clean_attachment({'attachTo': 'leaf0'}, {'mode': 'append', 'nodes': [{'id': 'copy', 'label': '技术0'}]}, context, '')

    def test_node_expansion_requires_existing_attachment(self):
        prompt = '在当前节点下继续展开分析'
        self.assertEqual(resolve_mode(prompt, CTX), 'append')
        result = {'mode': 'append', 'nodes': [{'id': 'new', 'label': '细分'}]}
        clean_attachment({}, result, CTX, prompt)
        self.assertEqual(result['attachTo'], 'box1')
        for target in ['missing', 'box2']:
            with self.assertRaises(ValueError):
                clean_attachment({'attachTo': target}, result, CTX, prompt)
        with self.assertRaises(ValueError):
            clean_attachment({}, result, [{**c, 'selected': False} for c in CTX], prompt)
        separate = {'mode': 'append', 'nodes': [{'id': 'new'}]}
        clean_attachment({}, separate, CTX, '在旁边画一个独立流程图')
        self.assertNotIn('attachTo', separate)

    def test_intent_cases(self):
        for instruction, context, expected in [
            ('把选中的矩形改成红色', CTX, 'modify'), ('删除选中的形状', CTX, 'modify'),
            ('再加一个蓝色圆形', CTX, 'append'), ('在右侧加一个节点', CTX, 'append'),
            ('总结一下画布', CTX, 'summarize'), ('重新画一个房子', CTX, 'replace'),
            ('画一个红色矩形', [], 'replace'), ('再加一个节点', [], 'replace'),
            ('画一个总结报告封面', CTX, 'auto'), ('画一张流程图', CTX, 'auto'),
            ('把下面的内容画成流程图', CTX, 'auto'),
        ]:
            with self.subTest(instruction=instruction):
                self.assertEqual(resolve_mode(instruction, context), expected)

    def test_styles_survive_all_content_types(self):
        style = {'strokeColor': '#ff0000', 'backgroundColor': '#ffeeaa', 'textColor': '#0000ff',
                 'strokeWidth': 3, 'roughness': 0, 'opacity': 0, 'strokeStyle': 'dashed'}
        drawing = gateway._clean_drawing({'elements': [{'type': 'rectangle', 'x': 0, 'y': 0, 'width': 100, 'height': 50, **style}]})
        diagram = gateway._clean_diagram({'nodes': [{'id': 'a', 'label': 'A', **style}, {'id': 'b', 'label': 'B'}],
                                          'edges': [{'source': 'a', 'target': 'b', **style}]})
        table = gateway._clean_component({'kind': 'table', 'headers': ['A'], 'rows': [[0]], **style})
        for item in [drawing['elements'][0], diagram['nodes'][0], diagram['edges'][0], table]:
            for key, value in style.items():
                self.assertEqual(item[key], value)
            self.assertEqual(item['fillStyle'], 'solid')

    def test_style_validation_and_text(self):
        self.assertEqual(clean_style({'strokeColor': 'url(https://invalid)', 'opacity': float('nan')}), {})
        self.assertEqual(clean_style({'strokeColor': 'red'})['strokeColor'], '#e03131')
        self.assertIsNone(gateway._num(float('nan')))
        self.assertIsNone(gateway._num(float('inf')))
        text = gateway._clean_drawing({'elements': [{'type': 'text', 'x': 0, 'y': 0, 'text': '你好', 'textColor': '#123456'}]})
        self.assertEqual(text['elements'][0]['text'], '你好')

    def test_patch_selection_and_ids_are_enforced(self):
        for edits in [[{'id': 'missing', 'delete': True}], [{'id': 'box2', 'delete': True}], [{'id': 'box1', 'x': 0}]]:
            with self.assertRaises(ValueError):
                clean_edits({'edits': edits}, CTX)
        self.assertEqual(clean_edits({'edits': [{'id': 'box1', 'backgroundColor': '#ff0000'}]}, CTX)['edits'][0]['fillStyle'], 'solid')

    def test_explicit_intent_overrides_incorrect_model_mode(self):
        provider = Mock()
        provider.complete.return_value = json.dumps({'mode': 'replace', 'edits': [{'id': 'box1', 'strokeColor': '#ff0000'}]})
        with patch.object(gateway, 'get_default_provider', return_value=provider):
            result = gateway.generate_board_content(None, '把选中的框边框改成红色', context=CTX)
        self.assertEqual(result['mode'], 'modify')

    def test_invalid_auto_mode_retries_instead_of_replacing_canvas(self):
        provider = Mock()
        provider.complete.side_effect = [json.dumps({'nodes': [{'label': 'A'}]}), json.dumps({'mode': 'append', 'nodes': [{'label': 'A'}]})]
        with patch.object(gateway, 'get_default_provider', return_value=provider):
            result = gateway.generate_board_content(None, '流程图', context=CTX)
        self.assertEqual(result['mode'], 'append')
        self.assertEqual(provider.complete.call_count, 2)

    def test_context_is_valid_json_and_keeps_selected_elements_first(self):
        context = [{'id': str(i), 'text': 'x' * 1000} for i in range(200)] + [CTX[0]]
        formatted = _format_board_context(context)
        self.assertLessEqual(len(formatted), 30000)
        self.assertEqual(json.loads(formatted)[0]['id'], 'box1')
        prompt = build_board_prompt('把选中框改成蓝色', 'modify', CTX)
        self.assertIn('edits', prompt)
        self.assertIn('backgroundColor', prompt)

    def test_invalid_part_does_not_silently_drop_half_the_request(self):
        with self.assertRaises(ValueError):
            gateway._clean_content({'parts': [{'type': 'diagram', 'nodes': [{'label': 'A'}]}, {'type': 'drawing', 'elements': []}]})


if __name__ == '__main__':
    unittest.main()
