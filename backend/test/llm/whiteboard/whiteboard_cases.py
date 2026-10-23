"""50 synthetic whiteboard conversations. All turns use the product's auto mode.

Each conversation has an initial canvas, user utterances, machine-checkable
expectations and a visual review focus. Multi-turn conversations use the previous
turn's result as context rather than replaying a fixed canned response.
"""
from copy import deepcopy

SCENE = [
    {'id': 'start', 'type': 'rectangle', 'text': '开始', 'x': 0, 'y': 0, 'width': 160, 'height': 80,
     'strokeColor': '#000000', 'backgroundColor': '#ffffff', 'textColor': '#000000', 'roughness': 1, 'opacity': 100},
    {'id': 'end', 'type': 'ellipse', 'text': '结束', 'x': 300, 'y': 0, 'width': 160, 'height': 80,
     'strokeColor': '#000000', 'backgroundColor': '#ffffff', 'textColor': '#000000', 'roughness': 1, 'opacity': 100},
    {'id': 'edge', 'type': 'arrow', 'x': 160, 'y': 40, 'points': [[0, 0], [140, 0]],
     'fromId': 'start', 'toId': 'end', 'strokeColor': '#000000', 'strokeWidth': 2, 'strokeStyle': 'solid'},
]


def check(collection, **rules):
    return {'collection': collection, **rules}


def turn(prompt, mode='replace', checks=None, **extra):
    return {'user': prompt, 'expect': {'mode': mode, 'checks': checks or [], **extra}}


def patch_turn(prompt, target='start', **attributes):
    return turn(prompt, 'modify', [check('edits', exact=[{'id': target, **attributes}])])


def case(number, group, name, turns, canvas='empty', selected=None, review='检查图形比例、文字可读性、布局和指令一致性'):
    context = deepcopy(SCENE) if canvas == 'existing' else []
    if selected:
        for item in context:
            item['selected'] = item['id'] in selected
    return {'id': f'WB{number:03d}', 'group': group, 'name': name,
            'initial_context': context, 'turns': turns, 'visual_review': review}


CASES = [
    case(1, 'drawing', '精确数量与边框填充双色', [turn('只画一个矩形，填充纯红色 #ff0000，边框蓝色 #0000ff，不要文字。', checks=[check('elements', count=1, all={'type': 'rectangle', 'backgroundColor': '#ff0000', 'strokeColor': '#0000ff', 'fillStyle': 'solid'})])]),
    case(2, 'drawing', '无填充圆形', [turn('画一个无填充的圆形，边框 #1971c2，完全平滑，宽高相等。', checks=[check('elements', count=1, all={'type': 'ellipse', 'backgroundColor': 'transparent', 'strokeColor': '#1971c2', 'roughness': 0}, equal_fields=['width', 'height'])])]),
    case(3, 'drawing', '图形内文字和文字色', [turn('只画一个菱形，里面写“是否通过”，填充 #1971c2，文字 #ffffff。', checks=[check('elements', count=1, all={'type': 'diamond', 'backgroundColor': '#1971c2', 'textColor': '#ffffff', 'label': {'text': '是否通过'}})])]),
    case(4, 'text', '独立中文文字和字号', [turn('只写“你好世界”，文字 #0000ff，字号32，不要边框或其他图形。', checks=[check('elements', count=1, all={'type': 'text', 'text': '你好世界', 'fontSize': 32}, color='#0000ff')])]),
    case(5, 'drawing', '同一图画中的两个对象', [turn('在同一幅画里画两个图形：左边红色矩形 #ff0000，右边蓝色圆形 #0000ff，都为纯色填充，不要连线或文字。', checks=[check('elements', count=2, contains=[{'type': 'rectangle', 'backgroundColor': '#ff0000'}, {'type': 'ellipse', 'backgroundColor': '#0000ff'}])])]),
    case(6, 'drawing', '折线和负坐标', [turn('只画一条红色 #ff0000 的L形折线，不要箭头，三个折点，先水平向右，再垂直向下。', checks=[check('elements', count=1, all={'type': 'line', 'strokeColor': '#ff0000'}, points_count=3)])]),
    case(7, 'drawing', '独立箭头', [turn('只画一根从左向右的绿色 #2f9e44 箭头，线宽4，使用虚线。', checks=[check('elements', count=1, all={'type': 'arrow', 'strokeColor': '#2f9e44', 'strokeWidth': 4, 'strokeStyle': 'dashed'})])]),
    case(8, 'drawing', '具体人物不是流程图', [turn('画一个举手的简笔画小人，圆形头、线条身体和四肢，所有线条 #1971c2，不要文字和流程图。', checks=[check('elements', min=5, all={'strokeColor': '#1971c2'}, contains=[{'type': 'ellipse'}, {'type': 'line'}])])], review='人工检查举手姿势、身体部件连接和比例，结构断言不评价绘画美观'),
    case(9, 'drawing', '房屋轮廓', [turn('画一个简笔画小房子，矩形墙体、三角形屋顶、一扇门和一扇窗，不要文字和流程图。', checks=[check('elements', min=4, contains=[{'type': 'rectangle'}, {'type': 'line'}])])], review='人工检查屋顶在墙体上方，门窗位于墙体内且没有悬空'),
    case(10, 'drawing', '组合自然景物', [turn('画一幅简笔画：左上角黄色太阳 #ffd43b，右边一朵云，所有图形无文字，不要流程图。', checks=[check('elements', min=2, contains=[{'type': 'ellipse', 'backgroundColor': '#ffd43b'}])])], review='人工检查太阳和云的相对位置及可辨识性'),
    case(11, 'style', '只改选中图形填充', [patch_turn('把选中图形的填充改为纯红色 #ff0000，其他属性不变。', backgroundColor='#ff0000', fillStyle='solid')], 'existing', ['start']),
    case(12, 'style', '边框色不影响填充或文字', [patch_turn('只把选中框的边框改为 #0000ff，不改填充和文字。', strokeColor='#0000ff')], 'existing', ['start']),
    case(13, 'style', '文字色不影响边框', [patch_turn('只把选中框内文字改为 #ff0000，边框和填充保持原样。', textColor='#ff0000')], 'existing', ['start']),
    case(14, 'style', '不透明度', [patch_turn('把选中框的不透明度设为35%，其余不变。', opacity=35)], 'existing', ['start']),
    case(15, 'style', '平滑风格零值', [patch_turn('选中的框不要抖动的手绘线，改为完全平滑，手绘程度为0，其余不变。', roughness=0)], 'existing', ['start']),
    case(16, 'style', '独立线宽', [patch_turn('只把选中框的线宽改为4。', strokeWidth=4)], 'existing', ['start']),
    case(17, 'style', '只改箭头线型', [patch_turn('只把选中的箭头改为虚线，其他元素和属性不变。', target='edge', strokeStyle='dashed')], 'existing', ['edge']),
    case(18, 'style', '点线边框', [patch_turn('把选中的框边框改为点线，不改颜色或线宽。', strokeStyle='dotted')], 'existing', ['start']),
    case(19, 'style', '取消填充', [patch_turn('把选中的框改为无填充，其余属性不变。', backgroundColor='transparent')], 'existing', ['start']),
    case(20, 'style', '交叉线填充', [patch_turn('把选中框填充色改为 #00ff00，填充样式为交叉线，不是纯色。', backgroundColor='#00ff00', fillStyle='cross-hatch')], 'existing', ['start']),
    case(21, 'diagram', '三节点流程图及连线样式', [turn('画开始、审批、结束三个节点的流程图，按顺序连接，节点填充 #ffff00，连线为红色 #ff0000 虚线。', checks=[check('nodes', count=3, all={'backgroundColor': '#ffff00'}, labels=['开始', '审批', '结束']), check('edges', count=2, all={'strokeColor': '#ff0000', 'strokeStyle': 'dashed'})])]),
    case(22, 'diagram', '条件分支标签', [turn('画三个节点：是否通过（菱形），通过后到归档，不通过到退回。两条分支分别标“通过”“不通过”，不要增加其他节点。', checks=[check('nodes', count=3, contains=[{'shape': 'diamond'}]), check('edges', count=2, labels=['通过', '不通过'])])]),
    case(23, 'diagram', '回边循环', [turn('画只有A、B、C三个节点的循环流程图，A到B，B到C，C回到A。', checks=[check('nodes', count=3, labels=['A', 'B', 'C']), check('edges', count=3)], connections=[['A', 'B'], ['B', 'C'], ['C', 'A']])], review='回边从侧边绕行，不穿过节点文字'),
    case(24, 'diagram', '允许无连线节点', [turn('画两个互不相连的流程节点，文字分别为“独立A”和“独立B”，明确不要连线。', checks=[check('nodes', count=2, labels=['独立A', '独立B']), check('edges', count=0)])]),
    case(25, 'diagram', '组织结构树', [turn('画五节点组织图：总经理下属研发部和销售部，研发部下属前端组和后端组。不要增加人员。', checks=[check('nodes', count=5, labels=['总经理', '研发部', '销售部', '前端组', '后端组']), check('edges', count=4)], connections=[['总经理', '研发部'], ['总经理', '销售部'], ['研发部', '前端组'], ['研发部', '后端组']])]),
    case(26, 'text', '多行中英混排', [turn('只写一块独立文字，第一行“项目计划”，第二行“Sprint 1”，第三行“2026-10-23”，必须保留换行，字号24。', checks=[check('elements', count=1, all={'type': 'text', 'text': '项目计划\nSprint 1\n2026-10-23', 'fontSize': 24})])]),
    case(27, 'table', '零值与空单元格', [turn('生成表格，表头为物品、数量、备注，数据两行：[苹果,0,空字符串]、[梨,2,已到货]。0和空单元格不能丢失。', checks=[check('tables', count=1, all={'headers': ['物品', '数量', '备注'], 'rows': [['苹果', '0', ''], ['梨', '2', '已到货']]})])]),
    case(28, 'table', '表格颜色和原文', [turn('生成只有两列两行数据的表格：姓名、角色；张三、开发；李四、测试。填充 #fff3bf，文字 #000000。', checks=[check('tables', count=1, all={'headers': ['姓名', '角色'], 'rows': [['张三', '开发'], ['李四', '测试']], 'backgroundColor': '#fff3bf', 'textColor': '#000000'})])]),
    case(29, 'mixed', '流程图加表格', [turn('左边画开始到结束的两节点流程图，旁边另放一个表格：姓名、角色；张三、开发。', checks=[check('parts', count=2, contains=[{'type': 'diagram'}, {'type': 'component'}]), check('nodes', count=2), check('tables', count=1)])]),
    case(30, 'mixed', '流程图加具体图画', [turn('生成两个独立部分：一个开始到结束的流程图，旁边一个蓝色 #0000ff 的圆形图案。', checks=[check('parts', count=2, contains=[{'type': 'diagram'}, {'type': 'drawing'}]), check('elements', count=1, all={'type': 'ellipse', 'backgroundColor': '#0000ff'})])]),
    case(31, 'intent', '追加保持已有内容', [turn('在现有画布旁边再加一个绿色 #00ff00 的圆形，不能重画已有内容。', 'append', [check('elements', count=1, all={'type': 'ellipse', 'backgroundColor': '#00ff00'})])], 'existing'),
    case(32, 'intent', '明确整体重画', [turn('清空当前画布重新画一个红色 #ff0000 的矩形，不保留任何旧内容。', checks=[check('elements', count=1, all={'type': 'rectangle', 'backgroundColor': '#ff0000'})])], 'existing'),
    case(33, 'scope', '删除选中对象', [patch_turn('删除选中的框，其他内容保留。', delete=True)], 'existing', ['start']),
    case(34, 'scope', '未选中时按名称删除', [patch_turn('只删除文字为“结束”的节点，其他内容保留。', target='end', delete=True)], 'existing'),
    case(35, 'summary', '整体汇总不修改', [turn('总结一下这张画布，不修改画布。', 'summarize', summary_contains=['开始', '结束'])], 'existing'),
    case(36, 'summary', '只解释选中元素', [turn('只总结选中的这部分图形，它是什么、写着什么，不要改动，不要提及未选中的元素或它们的文字。', 'summarize', summary_contains=['开始'], summary_excludes=['结束'])], 'existing', ['start']),
    case(37, 'scope', '同时修改两个选中对象', [turn('把选中的两个图形填充均改为纯红色 #ff0000，其他不变。', 'modify', [check('edits', count=2, all={'backgroundColor': '#ff0000', 'fillStyle': 'solid'}, ids=['start', 'end'])])], 'existing', ['start', 'end']),
    case(38, 'intent', '否定重画只改文字色', [patch_turn('不要新建，不要重画，只把“开始”的文字颜色改为 #ff0000。', textColor='#ff0000')], 'existing'),
    case(39, 'boundary', '空请求提示', [turn('', error_contains='请输入操作描述')]),
    case(40, 'boundary', '空画布汇总提示', [turn('总结一下画布', error_contains='画布是空的')]),
    case(41, 'conversation', '改色后再取消填充', [patch_turn('把选中框填充改为纯红色 #ff0000。', backgroundColor='#ff0000', fillStyle='solid'), patch_turn('现在把它的填充取消，边框和文字保持原样。', backgroundColor='transparent')], 'existing', ['start']),
    case(42, 'conversation', '改名后按新名字改文字色', [patch_turn('把“开始”改名为“申请提交”，其他不变。', text='申请提交'), patch_turn('把“申请提交”的文字改为蓝色 #0000ff，其他不变。', textColor='#0000ff')], 'existing'),
    case(43, 'conversation', '虚线恢复实线', [patch_turn('把选中的箭头改为红色 #ff0000 虚线。', target='edge', strokeColor='#ff0000', strokeStyle='dashed'), patch_turn('现在恢复实线，保留红色。', target='edge', strokeStyle='solid')], 'existing', ['edge']),
    case(44, 'conversation', '切换选区后修改', [patch_turn('把选中的框边框改为 #ff0000。', strokeColor='#ff0000'), {**patch_turn('这次把选中图形边框改为 #0000ff，不要影响刚才的框。', target='end', strokeColor='#0000ff'), 'select': ['end']}], 'existing', ['start']),
    case(45, 'conversation', '追加后定位新对象', [turn('旁边再加一个绿色圆形 #00ff00。', 'append', [check('elements', count=1, all={'type': 'ellipse', 'backgroundColor': '#00ff00'})]), turn('只把刚加的绿色圆形填充改成纯蓝色 #0000ff，其他内容不变。', 'modify', [check('edits', count=1, all={'backgroundColor': '#0000ff', 'fillStyle': 'solid'})], target_types=['ellipse'], target_before={'backgroundColor': '#00ff00'})], 'existing'),
    case(46, 'conversation', '新建后连续改色', [turn('画一个纯红色矩形 #ff0000。', checks=[check('elements', count=1, all={'type': 'rectangle', 'backgroundColor': '#ff0000'})]), turn('将刚才的矩形填充改为纯蓝色 #0000ff。', 'modify', [check('edits', count=1, all={'backgroundColor': '#0000ff', 'fillStyle': 'solid'})], target_types=['rectangle'])]),
    case(47, 'conversation', '重画后汇总新内容', [turn('重新画一个流程图，只有“提交”和“完成”两个节点，提交指向完成。', checks=[check('nodes', count=2, labels=['提交', '完成']), check('edges', count=1)]), turn('总结一下现在的画布。', 'summarize', summary_contains=['提交', '完成'], summary_excludes=['开始', '结束'])], 'existing'),
    case(48, 'conversation', '透明度零值再恢复', [patch_turn('将选中框的不透明度设为0，其他属性不变。', opacity=0), patch_turn('将选中框的不透明度恢复为100，其他属性不变。', opacity=100)], 'existing', ['start']),
    case(49, 'vision', '图片识别单个图形与颜色', [{**turn('按附图重现这个图形，保持形状、填充色和边框色，只输出一个图形，不要文字。', checks=[check('elements', count=1, all={'type': 'ellipse', 'backgroundColor': '#00ff00', 'strokeColor': '#0000ff'})]), 'image': 'circle.png'}], review='人工对比参考图中的圆形比例、纯绿色填充和蓝色边框'),
    case(50, 'vision', '图片识别流程关系与文字', [{**turn('将附图转为流程图，保留两个节点中的A和B及A到B的箭头，不要添加节点。', checks=[check('nodes', count=2, labels=['A', 'B']), check('edges', count=1)], connections=[['A', 'B']]), 'image': 'flow.png'}], review='人工核对A在左、B在右及箭头方向；当前自动布局可能调整为纵向'),
]

assert len(CASES) == 50 and len({c['id'] for c in CASES}) == 50
