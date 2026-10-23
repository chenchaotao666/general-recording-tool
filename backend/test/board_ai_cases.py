"""Synthetic prompts for reproducible live board AI evaluation (no user canvas data)."""
SCENE = [
    {'id': 'box1', 'type': 'rectangle', 'text': '开始', 'x': 0, 'y': 0, 'width': 140, 'height': 80,
     'backgroundColor': '#ffffff', 'strokeColor': '#000000'},
    {'id': 'box2', 'type': 'ellipse', 'text': '结束', 'x': 300, 'y': 0, 'width': 140, 'height': 80},
    {'id': 'arrow1', 'type': 'arrow', 'x': 140, 'y': 40, 'points': [[0, 0], [160, 0]], 'fromId': 'box1', 'toId': 'box2'},
]
SELECTED = [{**c, **({'selected': True} if c['id'] == 'box1' else {})} for c in SCENE]
CASES = [
    {'id': 'red_rectangle', 'prompt': '画一个矩形，纯红色填充 #ff0000、蓝色边框 #0000ff，不要文字，不要其他图形。', 'context': [], 'mode': 'auto', 'expect': 'replace'},
    {'id': 'selected_color', 'prompt': '把选中的框填充改成 #ff0000 纯红色，边框改为 #0000ff 蓝色，其他内容和位置不变。', 'context': SELECTED, 'mode': 'auto', 'expect': 'modify'},
    {'id': 'append_circle', 'prompt': '再加一个绿色圆形，填充 #00ff00，不能修改已有内容。', 'context': SCENE, 'mode': 'auto', 'expect': 'append'},
    {'id': 'diagram_colors', 'prompt': '画一个只有开始、审批、结束三个节点的审批流程图，节点填充 #ffff00，箭头红色 #ff0000、虚线。', 'context': [], 'mode': 'auto', 'expect': 'replace'},
    {'id': 'delete_selected', 'prompt': '删除选中的框，其余元素保留。', 'context': SELECTED, 'mode': 'auto', 'expect': 'modify'},
    {'id': 'standalone_text', 'prompt': '只写一段文字“你好世界”，文字为蓝色 #0000ff，字号32，不要矩形、流程图或其他图形。', 'context': [], 'mode': 'auto', 'expect': 'replace'},
    {'id': 'summary', 'prompt': '总结一下这张画布，不修改画布。', 'context': SCENE, 'mode': 'auto', 'expect': 'summarize'},
    {'id': 'mixed_parts', 'prompt': '画一个两节点流程图（开始到结束），旁边另放一个人员表格，表头姓名、角色，内容张三、开发。', 'context': [], 'mode': 'auto', 'expect': 'replace'},
    {'id': 'explicit_append', 'prompt': '画一个紫色矩形，填充 #800080。', 'context': SCENE, 'mode': 'append', 'expect': 'append'},
    {'id': 'outline_only', 'prompt': '把选中的框改成无填充，边框为 #e03131 红色虚线，线宽4，完全平滑，保持文字不变。', 'context': SELECTED, 'mode': 'auto', 'expect': 'modify'},
    {'id': 'text_color_only', 'prompt': '不要重画，只把“开始”节点的文字颜色改为 #ff0000，边框和填充都不动。', 'context': SCENE, 'mode': 'auto', 'expect': 'modify'},
    {'id': 'edge_color_only', 'prompt': '只将两个节点之间的箭头改成 #0000ff 蓝色，虚线，线宽3，节点不动。', 'context': SCENE, 'mode': 'auto', 'expect': 'modify'},
    {'id': 'rename_label', 'prompt': '将选中框里的“开始”改为“申请提交”，不改颜色和大小位置。', 'context': SELECTED, 'mode': 'auto', 'expect': 'modify'},
    {'id': 'drawing_not_diagram', 'prompt': '画一个简笔画小人，举起右手，头用圆形、身体和四肢用线，线条颜色 #1971c2，不要流程图，不要文字。', 'context': [], 'mode': 'auto', 'expect': 'replace'},
    {'id': 'table_not_summary', 'prompt': '用一个表格总结两个方案：方案A便宜但慢，方案B贵但快。列为方案、成本、速度。不要文字汇总段落。', 'context': SCENE, 'mode': 'auto', 'expect': 'replace'},
]


def validate(case, result):
    assert result['mode'] == case['expect'], f"mode={result.get('mode')}"
    parts = result.get('parts') or [result]
    elements = [e for p in parts for e in p.get('elements', [])]
    edits = result.get('edits', [])
    cid = case['id']
    if cid == 'red_rectangle':
        assert len(elements) == 1 and elements[0]['type'] == 'rectangle'
        assert elements[0]['backgroundColor'] == '#ff0000' and elements[0]['strokeColor'] == '#0000ff'
        assert elements[0]['fillStyle'] == 'solid'
    elif cid == 'selected_color':
        assert len(edits) == 1 and edits[0]['id'] == 'box1'
        assert edits[0]['backgroundColor'] == '#ff0000' and edits[0]['strokeColor'] == '#0000ff'
    elif cid == 'append_circle':
        assert len(elements) == 1 and elements[0]['type'] == 'ellipse' and elements[0]['backgroundColor'] == '#00ff00'
    elif cid == 'diagram_colors':
        nodes = [n for p in parts for n in p.get('nodes', [])]
        edges = [e for p in parts for e in p.get('edges', [])]
        assert len(nodes) == 3 and len(edges) >= 2
        assert all(n.get('backgroundColor') == '#ffff00' for n in nodes)
        assert all(e.get('strokeColor') == '#ff0000' and e.get('strokeStyle') == 'dashed' for e in edges)
    elif cid == 'delete_selected':
        assert edits == [{'id': 'box1', 'delete': True}]
    elif cid == 'standalone_text':
        assert len(elements) == 1 and elements[0]['type'] == 'text' and elements[0]['text'] == '你好世界'
        assert elements[0].get('textColor', elements[0].get('strokeColor')) == '#0000ff' and elements[0]['fontSize'] == 32
    elif cid == 'summary':
        assert result.get('summary') and '开始' in result['summary']
    elif cid == 'mixed_parts':
        assert {p['type'] for p in parts} == {'diagram', 'component'}
    elif cid == 'explicit_append':
        assert len(elements) == 1 and elements[0]['backgroundColor'] == '#800080'
    elif cid == 'outline_only':
        assert len(edits) == 1 and edits[0]['id'] == 'box1'
        assert all(edits[0].get(k) == v for k, v in {'backgroundColor': 'transparent', 'strokeColor': '#e03131', 'strokeStyle': 'dashed', 'strokeWidth': 4, 'roughness': 0}.items())
    elif cid == 'text_color_only':
        assert edits == [{'id': 'box1', 'textColor': '#ff0000'}]
    elif cid == 'edge_color_only':
        assert len(edits) == 1 and edits[0]['id'] == 'arrow1'
        assert edits[0]['strokeColor'] == '#0000ff' and edits[0]['strokeStyle'] == 'dashed' and edits[0]['strokeWidth'] == 3
    elif cid == 'rename_label':
        assert edits == [{'id': 'box1', 'text': '申请提交'}]
    elif cid == 'drawing_not_diagram':
        assert elements and all(e['type'] in ('ellipse', 'line') for e in elements)
        assert all(e.get('strokeColor') == '#1971c2' for e in elements)
    elif cid == 'table_not_summary':
        assert len(parts) == 1 and parts[0]['type'] == 'component'
        assert len(parts[0]['headers']) == 3 and len(parts[0]['rows']) == 2
