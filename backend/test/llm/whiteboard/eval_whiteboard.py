"""50-conversation evaluation of the hand-drawn board's real AI endpoint service.

Run from any directory: python eval_whiteboard.py --list | --live [WB001 ...]
Only synthetic canvas context is sent; no business rows or canvases are changed.
Multi-turn state is a semantic simulator, NOT an Excalidraw rendering test.
"""
import argparse
import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))
from app.database import SessionLocal
from app.models import LLMProvider
from app.services.llm.gateway import generate_board_content
from whiteboard_cases import CASES


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def subset(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and subset(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(subset(a, e) for a, e in zip(actual, expected))
    return actual == expected


def collect(result, name):
    parts = result.get('parts') or [result]
    if name == 'parts':
        return parts
    if name == 'tables':
        return [p for p in parts if p.get('type') == 'component' and p.get('kind') == 'table']
    if name == 'edits':
        return result.get('edits', [])
    return [item for part in parts for item in part.get(name, [])]


def validate(result, expected, context):
    require(result.get('mode') == expected['mode'], f"操作类型应为 {expected['mode']}，实际为 {result.get('mode')}")
    for rule in expected.get('checks', []):
        items = collect(result, rule['collection'])
        prefix = rule['collection']
        if 'count' in rule:
            require(len(items) == rule['count'], f"{prefix} 数量应为 {rule['count']}，实际为 {len(items)}")
        for limit, compare in [('min', lambda a, b: a >= b), ('max', lambda a, b: a <= b)]:
            if limit in rule:
                require(compare(len(items), rule[limit]), f"{prefix} 数量不满足 {limit}={rule[limit]}")
        if 'all' in rule:
            require(bool(items) and all(subset(item, rule['all']) for item in items), f"{prefix} 属性不满足 {rule['all']}")
        if 'contains' in rule:
            for desired in rule['contains']:
                require(any(subset(item, desired) for item in items), f"{prefix} 缺少 {desired}")
        if 'exact' in rule:
            comparable = items
            if prefix == 'edits':
                # Repeating an unchanged attribute is harmless. Reject extra
                # changes, not redundant serialization of the previous state.
                by_id = {c['id']: c for c in context}
                expected_by_id = {e['id']: e for e in rule['exact']}
                comparable = [{k: v for k, v in item.items()
                               if k in expected_by_id.get(item.get('id'), {})
                               or k not in by_id.get(item.get('id'), {})
                               or by_id[item['id']][k] != v} for item in items]
            require(len(comparable) == len(rule['exact']) and all(any(item == value for item in comparable) for value in rule['exact']), f"{prefix} 应只产生这些变更 {rule['exact']}，实际为 {items}")
        for name, prop in [('labels', 'label'), ('ids', 'id')]:
            if name in rule:
                require(sorted(item.get(prop, '') for item in items) == sorted(rule[name]), f"{prefix} {name} 不符")
        if 'equal_fields' in rule:
            a, b = rule['equal_fields']
            require(all(item.get(a) == item.get(b) for item in items), f"{prefix} 的 {a} 和 {b} 应相等")
        if 'points_count' in rule:
            require(all(len(item.get('points', [])) == rule['points_count'] for item in items), f"{prefix} 折点数量不符")
        if 'color' in rule:
            require(all(item.get('textColor', item.get('strokeColor')) == rule['color'] for item in items), f"{prefix} 文字颜色不符")
    if 'connections' in expected:
        nodes = {node['id']: node['label'] for node in collect(result, 'nodes')}
        edges = {(nodes.get(e['source']), nodes.get(e['target'])) for e in collect(result, 'edges')}
        require(edges == {tuple(pair) for pair in expected['connections']}, f"连接方向或端点不符：{sorted(edges)}")
    for text in expected.get('summary_contains', []):
        require(text in result.get('summary', ''), f"汇总缺少 {text}")
    for text in expected.get('summary_excludes', []):
        require(text not in result.get('summary', ''), f"汇总不应包含 {text}")
    if 'target_types' in expected or 'target_before' in expected:
        by_id = {c['id']: c for c in context}
        for edit in result.get('edits', []):
            original = by_id.get(edit['id'], {})
            require(original.get('type') in expected.get('target_types', [original.get('type')]), '修改了错误类型的对象')
            require(subset(original, expected.get('target_before', {})), '没有定位到上一轮生成的目标')


def apply_context(context, result, turn_number):
    """Apply IDs/styles/content semantically. Does not claim pixel-perfect UI validation."""
    if result['mode'] == 'summarize':
        return deepcopy(context)
    if result.get('edits'):
        by_id = {c['id']: c for c in context}
        selected = {c['id'] for c in context if c.get('selected')}
        deleted = {e['id'] for e in result['edits'] if e.get('delete')}
        updated = deepcopy(by_id)
        for edit in result['edits']:
            require(edit['id'] in by_id and (not selected or edit['id'] in selected), '修改越过选区或引用无效ID')
            if not edit.get('delete'):
                updated[edit['id']].update(edit)
        output = [c for key, c in updated.items() if key not in deleted]
        for c in output:
            for key in ('fromId', 'toId'):
                if c.get(key) in deleted:
                    del c[key]
        return output
    generated = []
    for pi, part in enumerate(result.get('parts') or [result]):
        prefix = f't{turn_number}p{pi}_'
        if part.get('nodes'):
            for index, node in enumerate(part['nodes']):
                generated.append({**node, 'id': prefix + node['id'], 'type': {'rect': 'rectangle'}.get(node['shape'], node['shape']),
                                  'text': node['label'], 'x': 0, 'y': index * 160, 'width': 160, 'height': 80})
            for index, edge in enumerate(part.get('edges', [])):
                generated.append({**edge, 'id': prefix + f'e{index}', 'type': 'arrow', 'fromId': prefix + edge['source'], 'toId': prefix + edge['target']})
        elif part.get('elements'):
            for index, element in enumerate(part['elements']):
                item = {**element, 'id': prefix + f'd{index}'}
                if element.get('label'):
                    item['text'] = element['label']['text']
                generated.append(item)
        elif part.get('headers'):
            for r, row in enumerate([part['headers'], *part.get('rows', [])]):
                for c, text in enumerate(row):
                    generated.append({'id': prefix + f'r{r}c{c}', 'type': 'rectangle', 'text': text, 'x': c * 160, 'y': r * 50, 'width': 160, 'height': 50})
    if result['mode'] == 'append':
        return deepcopy(context) + generated
    if result['mode'] == 'modify' and any(c.get('selected') for c in context):
        return [deepcopy(c) for c in context if not c.get('selected')] + generated
    return generated


def run_case(case):
    started = time.monotonic()
    record = {'id': case['id'], 'group': case['group'], 'name': case['name'], 'turns': [], 'visual_review': case['visual_review']}
    context = deepcopy(case['initial_context'])
    for index, turn in enumerate(case['turns'], 1):
        if 'select' in turn:
            for item in context:
                item['selected'] = item['id'] in turn['select']
        entry = {'turn': index, 'user': turn['user'], 'context': deepcopy(context), 'expect': turn['expect']}
        record['turns'].append(entry)
        try:
            images = None
            if turn.get('image'):
                path = HERE / 'whiteboard_fixtures' / turn['image']
                images = ['data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')]
            try:
                with SessionLocal() as db:
                    result = generate_board_content(db, turn['user'], 'auto', context, images)
            except Exception as error:
                if turn['expect'].get('error_contains') and turn['expect']['error_contains'] in str(error):
                    entry.update(status='PASS', expected_error=str(error))
                    continue
                raise
            entry['result'] = result
            require('error_contains' not in turn['expect'], '预期返回提示错误，但模型生成了内容')
            validate(result, turn['expect'], context)
            context = apply_context(context, result, index)
            entry['status'] = 'PASS'
        except Exception as error:
            entry.update(status='FAIL', error=str(error) or type(error).__name__)
            break  # Later turns depend on this turn; do not fake success after failure.
    record['status'] = 'PASS' if len(record['turns']) == len(case['turns']) and all(t['status'] == 'PASS' for t in record['turns']) else 'FAIL'
    record['unexecuted_turns'] = len(case['turns']) - len(record['turns'])
    record['seconds'] = round(time.monotonic() - started, 2)
    return record


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ids', nargs='*', help='WB001 WB011 ...')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--live', action='store_true', help='Call the configured provider; consumes model quota')
    parser.add_argument('--group')
    parser.add_argument('--workers', type=int, default=2, choices=range(1, 5))
    parser.add_argument('--repeat', type=int, default=1, choices=range(1, 6))
    parser.add_argument('--output', type=Path, default=HERE / 'whiteboard_results.json')
    args = parser.parse_args()
    known = {c['id'] for c in CASES}
    if set(args.ids) - known:
        parser.error('Unknown case IDs: ' + ', '.join(set(args.ids) - known))
    cases = [c for c in CASES if (not args.ids or c['id'] in args.ids) and (not args.group or c['group'] == args.group)]
    if not cases:
        parser.error('No matching cases')
    if args.list:
        for case in cases:
            print(f"{case['id']} [{case['group']}] {case['name']} ({len(case['turns'])} turns)")
        return 0
    if not args.live:
        parser.error('Use --list to inspect or --live to call the model')
    with SessionLocal() as db:
        provider = db.query(LLMProvider).filter(LLMProvider.enabled.is_(True)).order_by(LLMProvider.is_default.desc(), LLMProvider.id).first()
        if provider is None:
            parser.error('No enabled model provider')
        model = {'type': provider.type, 'model': provider.model, 'vision_model': provider.vision_model}
    results = []
    for repeat in range(args.repeat):
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(run_case, c) for c in cases]):
                result = future.result()
                result['run'] = repeat + 1
                results.append(result)
                error = next((t.get('error', '') for t in result['turns'] if t['status'] == 'FAIL'), '')
                print(f"{result['id']} {result['status']} {result['seconds']}s {error[:180]}", flush=True)
                # Checkpoint after each case, preserving partial evidence on interruption.
                report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'provider': model,
                          'scope': 'Live model + server validation + semantic multi-turn context; visual/UI confirmation requires separate review',
                          'planned_conversations': len(cases) * args.repeat, 'completed': len(results),
                          'counts': dict(Counter(r['status'] for r in results)), 'results': sorted(results, key=lambda r: (r['run'], r['id']))}
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['counts'], ensure_ascii=False), flush=True)
    return 0 if all(r['status'] == 'PASS' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
