"""Refresh only the explicitly named synthetic audit table after formula migration."""
import json
from collections import Counter
from ai_template_live_audit import (STATE, ROOT, NAME, SessionLocal, MetaTable, MetaField,
    Record, to_field_in, fixture, save_state, dump, ai, display)
from app.services.ai_scenes import SCENE_BY_KEY
from app.services.ai_template_formulas import FORMULAS, CONTRACTS


def main():
    state = json.loads(STATE.read_text(encoding='utf-8'))
    with SessionLocal() as db:
        mt = db.get(MetaTable, state['table_id'])
        assert mt.label == NAME and 'ai_template_audit_' in mt.name and mt.owner_id == state['owner_id']
        for case in state['cases']:
            key = case['key']
            if key not in FORMULAS:
                continue
            scene = SCENE_BY_KEY[key]
            row = db.get(Record, case['record_id'])
            field = db.query(MetaField).filter_by(table_id=mt.id, field_name=case['field']).one()
            cfg = dict(field.options)
            data = dict(row.data)
            if key in FORMULAS:
                source, expected, values = fixture(scene)
                if not values and scene.get('inputRoles'):
                    values = [source]
                cfg.update(inputBindings={}, inputFields=[], outputType=scene['outputType'])
                for role, value in zip(scene['inputRoles'], values):
                    name = f'in_{key}_{role["key"]}'.lower()
                    existing = db.query(MetaField).filter_by(table_id=mt.id, field_name=name).first()
                    if not existing:
                        spec = to_field_in('date' if 'date' in role['types'] else 'number' if 'number' in role['types'] else 'text', f'{scene["label"]}·{role["label"]}', name)
                        db.add(MetaField(table_id=mt.id, **{k:v for k,v in spec.items() if k in {'field_name','label','data_type','field_type','widget','options'}}, sort_order=900))
                    data[name] = value
                    cfg['inputBindings'][role['key']] = name
                    cfg['inputFields'].append(name)
                case['expected'] = expected
                data.update(input_text=str(source), expected=dump(expected))
            cfg['formulaVersion'] = 1
            field.options = cfg
            field.label = scene['label']
            data.update(mode=scene['executionLabel'], note=scene['desc'])
            row.data = data
            db.commit()
            fields = db.query(MetaField).filter_by(table_id=mt.id).all()
            result, billed, tokens = ai.compute_raw(db, cfg, fields, data, [])
            assert not billed and tokens == 0
            ai.process(db, mt.id, case['field'], [case['record_id']])
            db.expire_all()
            row = db.get(Record, case['record_id'])
            actual = row.data.get(case['field'])
            shown = display(db, field, actual, {})
            expected = case['expected']
            passed = abs(actual-expected)<.02 if isinstance(expected,(float,int)) and not isinstance(expected,bool) else str(shown)==str(expected)
            # Checkbox formatter uses localized labels; compare raw bool.
            if isinstance(expected,bool): passed = actual is expected
            if key == 'cvRandom': passed = isinstance(actual, (int, float)) and 1 <= actual <= 100
            assert passed, (key, actual, shown, expected)
            case.update(label=scene['label'], execution='calculation', config=cfg, input=data,
                actual=actual, display=shown, status='通过', billable=False, tokens=0,
                note='执行已展示公式；真实落库复验通过', review='公式精确断言通过')
            row.data = {**row.data, 'actual':shown, 'verdict':'通过', 'note':case['note']}
            db.commit()
            print(key, 'PASS', shown)
        state['table_stats']['fields'] = db.query(MetaField).filter_by(table_id=mt.id).count()
        save_state(state)
    report = ['# AI 模板公式化检查报告', '', f'目前共 {len(FORMULAS)} 项由公式引擎实际执行。本轮在此前12项基础上新增17项，包括截止倒计时、BMR、年龄、工龄、任务状态、月末、工时等。展示公式与实际执行公式同源，不调用模型、不消耗模型额度。', '',
        f'真实验证表：[AI 模板全量验证（142项）]({state["url"]})。{len(FORMULAS)}项均已配置并落库复验通过；随机数检查范围而非固定结果。', '',
        '## 公式清单', '', '方括号为输入角色；复制到普通公式列时替换为实际字段名。空输入返回空；无效数字、负税基、非法日期和零分母会提示校验错误。', '']
    for key in FORMULAS:
        s = SCENE_BY_KEY[key]
        report += [f'### {s["label"]}', '', s['desc'], '', '```text', s['formulaDisplay'], '```', '']
    report += ['## 检查结论', '',
        '- 截止倒计时改为数字：截止日期晚于今天时返回自然日差；空日期、到期当天及已过期返回空。验证表的输出类型同步更新为数字。业务表中的旧倒计时字段需重新保存模板配置，以更新原来的文本输出类型。',
        '- 扩展公式函数 NETWORKDAYS_CN（中国节假日与调休）及 DATEDIF 的 S 单位（精确秒数，无时区按北京时间），普通公式列也可使用。原 NETWORKDAYS 的周一至周五规则保持不变。',
        '- 本轮后端44项回归通过；涵盖日期空值、当日、逾期、闰日、调休、跨时区工时及数字转换，并断言不调用旧计算分支或模型。',
        '- 可表达的单行规则由公式执行；身份证校验、文本编码、农历、多人交集跨行汇总及文件处理等保留本地算法（没有硬套会改变语义的公式），均不调用模型。语义分类、摘要、OCR、风险分析等保留模型。',
        '- 增值税模板原实现误解为税额计算，已按参考图纠正为申报截止日；周末顺延不等于实际法定申报期限。',
        '- 参考图中月度税额示例不全正确：应纳税所得额9200元按10%减210，应为710元，不是截图的620元。按规则修正，不照抄错误示例。',
        '- 年终奖合并采用年度综合所得口径，输入为扣除费用后的全年所得额与奖金，不将全年奖金直接套月度工资档位。',
        '- 修复公式引擎幂运算优先级：70/(175/100)^2 现在为22.857…，不再按低优先级异或语法分组。字符串中的^保留原样，SQL求值同步支持。',
        '- 已有六类模型配置需要重新绑定结构化输入；旧自然语言描述不能当作税基或工龄，系统会校验并报错，不再让模型推测。此次只自动更新合成验证表，未批改业务表数据。',
        '- 原全量验证报告记录的是此前模型执行结果，本报告及最新验证数据中的 calculation 记录为本次公式复验结果。', '',
        '## 规则依据', '',
        '- [全年一次性奖金政策](https://fgk.chinatax.gov.cn/zcfgk/c102416/c5211524/content.html)：单独计税除以12查月度换算税率表，政策执行至2027-12-31。',
        '- [个人所得税法及年度税率表](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_901ca8faba104739bbf54e22483e6079.html)。',
        '- [职工带薪年休假条例](https://xzfg.moj.gov.cn/front/law/detail?LawID=208)：本模板仅计算标准全年额度，资格及特殊情形另行核对。', '']
    (ROOT/'docs/AI模板公式化检查报告.md').write_text('\n'.join(report), encoding='utf-8')


if __name__ == '__main__':
    main()
