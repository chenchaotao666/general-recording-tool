"""Opt-in live evaluation: python scripts/eval_board_ai.py --live [--case ID]."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.services.llm.gateway import generate_board_content
from test.board_ai_cases import CASES, validate


def run(case):
    started = time.monotonic()
    item = {'id': case['id'], 'prompt': case['prompt']}
    try:
        with SessionLocal() as db:
            item['result'] = generate_board_content(db, case['prompt'], case['mode'], case['context'])
        validate(case, item['result'])
        item['passed'] = True
    except Exception as error:
        item['passed'] = False
        item['error'] = str(error) or type(error).__name__
    item['seconds'] = round(time.monotonic() - started, 2)
    return item


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Call the configured model; consumes model quota')
    parser.add_argument('--case', action='append')
    parser.add_argument('--output', default='../docs/whiteboard-ai-evaluation.json')
    args = parser.parse_args()
    if not args.live:
        parser.error('Use --live to explicitly enable model requests')
    cases = [c for c in CASES if not args.case or c['id'] in args.case]
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(run, c) for c in cases]):
            item = future.result()
            results.append(item)
            print(f"{item['id']}: {'PASS' if item['passed'] else 'FAIL'} ({item['seconds']}s)", flush=True)
    report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'passed': sum(r['passed'] for r in results), 'total': len(results), 'cases': results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"{report['passed']}/{report['total']} passed", flush=True)
    sys.exit(0 if report['passed'] == report['total'] else 1)
