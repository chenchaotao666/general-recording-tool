"""Whiteboard intent and supported visual attributes, shared by all output shapes."""
import math
import re

COLORS = {'red': '#e03131', 'blue': '#1971c2', 'green': '#2f9e44', 'yellow': '#ffd43b',
          'black': '#1e1e1e', 'white': '#ffffff', 'purple': '#9c36b5', 'orange': '#e8590c',
          'gray': '#868e96', 'grey': '#868e96', 'pink': '#d6336c',
          '红色': '#e03131', '蓝色': '#1971c2', '绿色': '#2f9e44', '白色': '#ffffff', '黑色': '#1e1e1e'}


def clean_style(data, *, fill_defaults=True):
    out = {}
    for key in ('strokeColor', 'backgroundColor', 'textColor'):
        value = str(data.get(key) or '').strip().lower()
        value = COLORS.get(value, value)
        if re.fullmatch(r'#[0-9a-f]{3}(?:[0-9a-f]{3})?', value) or value == 'transparent':
            out[key] = value
    for key, choices in {'fillStyle': {'solid', 'hachure', 'cross-hatch'},
                         'strokeStyle': {'solid', 'dashed', 'dotted'},
                         'textAlign': {'left', 'center', 'right'},
                         'verticalAlign': {'top', 'middle', 'bottom'}}.items():
        if isinstance(data.get(key), str) and data[key] in choices:
            out[key] = data[key]
    if data.get('fontFamily') in (1, 2, 3, 5, 6, 7, 8, 9) and not isinstance(data.get('fontFamily'), bool):
        out['fontFamily'] = data['fontFamily']
    for key, low, high in [('strokeWidth', 1, 8), ('roughness', 0, 2), ('opacity', 0, 100), ('fontSize', 12, 72)]:
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            out[key] = max(low, min(high, value))
    if fill_defaults and out.get('backgroundColor') not in (None, 'transparent'):
        out.setdefault('fillStyle', 'solid')
    return out


def is_node_expansion(description):
    return bool(re.search(r'续写|继续展开|展开分析|细化|扩展.*(?:节点|分支)|(?:节点|分支).*(?:展开|扩展|下面.*(?:加|增))', description))


def is_selected_style_edit(description, context):
    return (any(c.get('selected') for c in context)
            and bool(re.search(r'填充|边框|边线|描边|线型|线宽|线条|虚线|实线|透明度|文字色|字号|大号|小号|中号|对齐|字体|漫画风格', description))
            and not re.search(r'画一个|画一张|生成|重画|重绘|新增.*(?:节点|图形)|总结|解释|续写|展开', description))


def expansion_targets(description, context):
    nodes = {c['id']: c for c in context if c.get('type') in ('rectangle', 'ellipse', 'diamond')}
    match = re.search(r'第\s*([一二三四五六七八九十]|\d+)\s*层', description)
    if not match:
        return [key for key, c in nodes.items() if c.get('selected')]
    value = match.group(1)
    level = int(value) if value.isdigit() else '一二三四五六七八九十'.index(value) + 1
    edges = [(c.get('fromId'), c.get('toId')) for c in context
             if c.get('fromId') in nodes and c.get('toId') in nodes]
    incoming = {target for _, target in edges}
    frontier = set(nodes) - incoming
    visited = set(frontier)
    for _ in range(1, min(level, len(nodes) + 1)):
        frontier = {target for source, target in edges if source in frontier} - visited
        visited.update(frontier)
    return [key for key in nodes if key in frontier] if level > 0 else []


def clean_attachment(data, result, context, description):
    if result.get('parts') and (is_node_expansion(description) or any(p.get('attachTo') for p in data.get('parts', []))):
        raw_parts = data.get('parts', [])
        if len(raw_parts) != len(result['parts']):
            raise ValueError('展开分支数量不一致')
        targets = []
        for raw, part in zip(raw_parts, result['parts']):
            part['mode'] = result['mode']
            clean_attachment(raw, part, [{**c, 'selected': False} for c in context], '')
            if not part.get('attachTo'):
                raise ValueError('每个展开分支都必须指定 attachTo')
            targets.append(part['attachTo'])
        expected = expansion_targets(description, context)
        if len(set(targets)) != len(targets) or expected and set(targets) != set(expected):
            raise ValueError(f'必须分别展开全部目标节点，每个目标一个 part：{expected}')
        return
    target = data.get('attachTo')
    required = is_node_expansion(description) and bool(context) and result['mode'] == 'append'
    if not target and not required:
        return
    candidates = [c for c in context if c.get('type') in ('rectangle', 'ellipse', 'diamond')]
    selected = [c for c in candidates if c.get('selected')]
    if not target and len(selected) == 1:
        target = selected[0]['id']
    allowed = {c['id'] for c in candidates}
    expected = expansion_targets(description, context)
    if expected and (len(expected) != 1 or target != expected[0]):
        raise ValueError(f'必须分别展开全部目标节点，多目标使用 parts，每项带 attachTo：{expected}')
    if result['mode'] != 'append' or not isinstance(target, str) or target not in allowed:
        raise ValueError('节点展开必须返回 attachTo，值为上下文中目标节点的原始 ID')
    if selected and not re.search(r'第.+层', description) and target not in {c['id'] for c in selected}:
        raise ValueError('请在选中的节点下展开，不能连接其他节点')
    if not result.get('nodes') or result.get('parts'):
        raise ValueError('节点展开必须输出单个 diagram 的新增 nodes/edges，不得重新绘制原图')
    existing_labels = {str(c.get('text', '')).strip().casefold() for c in candidates} - {''}
    if any(str(n.get('label', '')).strip().casefold() in existing_labels for n in result['nodes']):
        raise ValueError('新增节点重复了已有节点名称，请直接生成更具体的下级分析，不要复制已有层级')
    result['attachTo'] = target


def resolve_mode(description, context):
    """Only override model routing for explicit intent. Ambiguous wording stays auto."""
    text = description.strip()
    if re.search(r'^(?:请|帮我|请帮我)?\s*(?:总结|汇总|概括|解释|说明)(?:一下)?(?:这|当前|选中|画布|图|内容|$)', text):
        return 'summarize'
    if not context:
        return 'replace'
    if is_selected_style_edit(text, context):
        return 'modify'
    if re.search(r'^(?:请|帮我|请帮我)?\s*(?:清空.*重画|重新画|重画|替换(?:整个|全部)?画布)', text):
        return 'replace'
    if is_node_expansion(text):
        return 'append'
    if re.search(r'^(?:请|帮我|请帮我)?\s*(?:再加|追加|新增|补充|添加|旁边.*画|在.{0,10}(?:旁边|右侧|左侧).*加)', text):
        return 'append'
    if re.search(r'^(?:请|帮我|请帮我)?\s*(?:修改|调整|删除|移除|改成|改为)', text) or re.search(
        r'^(?:请|帮我|请帮我)?\s*(?:把|将).*(?:改成|改为|修改|调整|设为|设置|删除|移除|变成|变为)', text
    ):
        return 'modify'
    return 'auto'


def clean_edits(data, context, description=''):
    by_id = {c['id']: c for c in context if isinstance(c.get('id'), str)}
    selected = {key for key, c in by_id.items() if c.get('selected')}
    edits = []
    seen = set()
    if not isinstance(data.get('edits'), list) or len(data['edits']) > 200:
        raise ValueError('edits 必须是最多 200 项的数组')
    for edit in data['edits']:
        if not isinstance(edit, dict):
            raise ValueError('edits 必须是对象数组')
        key = edit.get('id')
        if key not in by_id or key in seen or selected and key not in selected:
            raise ValueError('修改目标必须是上下文中允许修改的元素 ID，不能重复或越过选区')
        seen.add(key)
        if edit.get('delete') is True:
            edits.append({'id': key, 'delete': True})
            continue
        patch = clean_style(edit, fill_defaults=False)
        # Match the editor's text presets rather than inventing relative sizes or redrawing.
        if re.search(r'文字|字体|字号|对齐', description):
            for name, value in [('超大号', 36), ('大号', 28), ('中号', 20), ('小号', 16)]:
                if name in description:
                    patch['fontSize'] = value
                    break
            for name, value in [('左对齐', 'left'), ('右对齐', 'right'), ('水平居中', 'center')]:
                if name in description:
                    patch['textAlign'] = value
            for name, value in [('顶部对齐', 'top'), ('顶端对齐', 'top'), ('底部对齐', 'bottom'), ('垂直居中', 'middle')]:
                if name in description:
                    patch['verticalAlign'] = value
            if re.search(r'漫画字体|字体.*漫画', description):
                patch['fontFamily'] = 8
        if re.search(r'漫画风格|漫画家|线条.*漫画', description):
            patch['roughness'] = 2
            if not re.search(r'漫画字体|字体.*漫画', description):
                patch.pop('fontFamily', None)
        original = by_id[key]
        # Fill patterns are invisible on a transparent background. Preserve the existing
        # fill colour, or use the existing stroke colour when enabling a fill for the first time.
        requested_fill = None
        if re.search(r'交叉(?:线)?填充|网格填充', description):
            requested_fill = 'cross-hatch'
        elif re.search(r'(?:斜线|线条|排线)填充|填充.*(?:斜线|线条|排线)', description):
            requested_fill = 'hachure'
        elif re.search(r'纯色填充|实心填充|填充.*(?:纯色|实心)', description):
            requested_fill = 'solid'
        no_fill = bool(re.search(r'取消填充|去掉填充|无填充|透明填充|填充.*透明', description))
        if no_fill:
            patch['backgroundColor'] = 'transparent'
            patch.pop('fillStyle', None)
        elif requested_fill:
            patch['fillStyle'] = requested_fill
            if patch.get('backgroundColor', original.get('backgroundColor')) in (None, 'transparent'):
                patch['backgroundColor'] = (original.get('backgroundColor')
                    if original.get('backgroundColor') not in (None, 'transparent')
                    else original.get('strokeColor') if original.get('strokeColor') not in (None, 'transparent') else '#1e1e1e')
            # A request about fill is not a request to change the outline's line pattern.
            if not re.search(r'边框|边线|轮廓|描边', description):
                patch.pop('strokeStyle', None)
                patch.pop('strokeWidth', None)
        elif 'backgroundColor' in patch and patch['backgroundColor'] != 'transparent':
            # Changing a colour must not silently replace an existing hatch with solid fill.
            if description and not re.search(r'纯色|实心|斜线|排线|交叉|网格|填充样式', description):
                patch['fillStyle'] = original.get('fillStyle') or 'solid'
            else:
                patch.setdefault('fillStyle', original.get('fillStyle') or 'solid')
        if isinstance(edit.get('text'), str):
            patch['text'] = edit['text'][:1000]
        if not patch:
            raise ValueError('修改内容为空或包含不支持的属性')
        edits.append({'id': key, **patch})
    if not edits:
        raise ValueError('edits 不能为空')
    return {'mode': 'modify', 'title': str(data.get('title') or '修改画布')[:64], 'edits': edits}
