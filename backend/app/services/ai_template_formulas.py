"""Executable template formulas. The displayed expression is the executed expression."""
import math
from datetime import date, datetime, timedelta, timezone
from . import expr


def brackets(value, annual=False, tax=False):
    limits = [3000, 12000, 25000, 35000, 55000, 80000]
    rates = [.03, .1, .2, .25, .3, .35, .45]
    deductions = [0, 210, 1410, 2660, 4410, 7160, 15160]
    factor = 12 if annual else 1
    results = [f'{value}*{r}-{d*factor}' if tax else f'"{round(r*100)}%"' for r, d in zip(rates, deductions)]
    pairs = [f'{value}<={n*factor},{result}' for n, result in zip(limits, results)]
    return 'IFS(' + ','.join(pairs + ['TRUE,' + results[-1]]) + ')'


FORMULAS = {
    'fnIit': 'ROUND(MAX(0,' + brackets('[taxable]', tax=True) + '),2)',
    'fnIitLevel': brackets('[taxable]'),
    'fnBonusSeparate': brackets('([bonus]/12)'),
    'fnBonusMerge': brackets('([taxable]+[bonus])', annual=True),
    'hrLeave': 'IFS([years]<1,0,[years]<10,5,[years]<20,10,TRUE,15)',
    'pdStock': 'ROUND([opening]+[incoming]-[outgoing],4)',
    'pdStockAlert': 'IFS([stock]<=0,"缺货",[stock]<[minimum],"偏低",TRUE,"充足")',
    'pdHours': 'ROUND([value]*[total],2)',
    'pdDefect': 'ROUND([value]/[total]*100,2)',
    'stAttendance': '[value]/[total]>=0.95',
    'cvBmi': 'ROUND([weight]/([height]/100)^2,1)',
    'cvBmr': 'IF(OR([height]<=0,[weight]<=0,[age]<0),"",IF([gender]="男",ROUND(10*[weight]+6.25*[height]-5*[age]+5,0),IF([gender]="女",ROUND(10*[weight]+6.25*[height]-5*[age]-161,0),"")))',
    'deadlineCountdown': 'IF(ISBLANK([end]),"",IF([end]<=TODAY(),"",DATEDIF(TODAY(),[end],"D")))',
    'taskStatus': 'IF(NOT(ISBLANK([done])),"已完成",IF(ISBLANK([start]),"未开始",IF(ISBLANK([end]),"进行中",IF([end]<TODAY(),"已延期","进行中"))))',
    'hrAge': 'IF(ISBLANK([start]),"",IF([start]>TODAY(),"",DATEDIF([start],TODAY(),"Y")))',
    'hrSeniority': 'IF(ISBLANK([start]),"",IF([start]>TODAY(),"",ROUND(DATEDIF([start],TODAY(),"D")/365.25,1)))',
    'hrContract': 'IF(ISBLANK([end]),"",IFS([end]<TODAY(),"已到期",DATEDIF(TODAY(),[end],"D")<=30,"即将到期",TRUE,"生效中"))',
    'stHealthDays': 'IF(ISBLANK([end]),"",DATEDIF(TODAY(),[end],"D"))',
    'stHealthExpiry': 'IF(ISBLANK([start]),"",EDATE([start],12))',
    'orderShippingStatus': 'IF(ISBLANK([end]),"待发货",IF(ISBLANK([start]),"",IF(DATEDIF([start],[end],"D")>1,"延迟发货","已发货")))',
    'cvMonthEnd': 'DAY([date])=DAY(EOMONTH([date],0))',
    'cvMonthDays': 'DAY(EOMONTH([date],0))',
    'cvMileKm': 'ROUND([value]*1.609344,2)',
    'cvRandom': 'RANDBETWEEN(1,100)',
    'stHours': 'ROUND(DATEDIF([start],[end],"S")/3600,2)',
    'pdTicketTime': 'ROUND(DATEDIF([start],[end],"S")/3600,2)',
    'workdays': 'NETWORKDAYS_CN([start],[end])',
    'cvWordCount': 'LEN(SUBSTITUTE(TRIM([text])," ",""))',
}
# Reference template: next month's 15th, weekends only. Statutory extensions are not inferred.
_due = 'DATE(YEAR(EDATE([date],1)),MONTH(EDATE([date],1)),15)'
FORMULAS['fnVat'] = f'DATEADD({_due},IF(WEEKDAY({_due},2)>5,8-WEEKDAY({_due},2),0),"day")'

CONTRACTS = {
    'fnIit': [('taxable', '月度应纳税所得额（已扣除费用）')],
    'fnIitLevel': [('taxable', '月度应纳税所得额（已扣除费用）')],
    'fnBonusSeparate': [('bonus', '全年一次性奖金总额')],
    'fnBonusMerge': [('taxable', '全年应纳税所得额（不含本次奖金，已扣除费用）'), ('bonus', '并入综合所得的奖金')],
    'hrLeave': [('years', '累计工作年限（年）')],
    'fnVat': [('date', '所属期日期')],
}
DESCRIPTIONS = {
    'fnIit': '按月度换算税率表计算参考税额，输入为已扣除费用的月度应纳税所得额；不是居民工资累计预扣或年度汇算税额。',
    'fnIitLevel': '按月度换算税率表返回适用税率档位；输入是应纳税所得额，不是税前工资。',
    'fnBonusSeparate': '全年一次性奖金除以 12 后，按月度换算税率表返回单独计税税率；输出税率而非税额。政策适用至 2027-12-31。',
    'fnBonusMerge': '将奖金加到全年应纳税所得额后，按年度综合所得税率表返回边际税率；不是有效税率，也不代表奖金最终税额。',
    'hrLeave': '按累计工作年限计算标准全年年休假天数：不足1年0天，满1年5天，满10年10天，满20年15天。不包含入离职折算、已休抵扣及不享受年休假的特殊情形。',
    'fnVat': '所属期次月15日，遇周末顺延至周一。仅为申报截止日参考，法定节假日及税务机关公布的延期需另行核对。',
}


def enrich_formulas(scenes):
    for s in scenes:
        key = s['key']
        if key not in FORMULAS:
            continue
        if key in CONTRACTS:
            s['inputRoles'] = [dict(key=k, label=label, required=True,
                types=['date', 'text', 'formula'] if key == 'fnVat' else ['number', 'currency', 'formula', 'text'])
                for k, label in CONTRACTS[key]]
            s.update(desc=DESCRIPTIONS[key], input='multi', outputType='date' if key == 'fnVat' else 'number' if key in ('hrLeave', 'fnIit') else 'text')
        if key == 'fnVat':
            s['label'] = '计算增值税申报截止日'
        if key in ('cvMonthEnd', 'cvMonthDays', 'cvMileKm', 'cvRandom'):
            s['inputRoles'] = [] if key == 'cvRandom' else [dict(key='value' if key == 'cvMileKm' else 'date', label='英里' if key == 'cvMileKm' else '日期', required=True, types=['number', 'text', 'formula'] if key == 'cvMileKm' else ['date', 'text', 'formula'])]
        if key == 'cvWordCount':
            s['inputRoles'] = [dict(key='text', label='文本', required=True, types=['text', 'formula'])]
        if key == 'deadlineCountdown':
            s.update(outputType='number', desc='计算距计划完成日期的自然日天数；日期为空、到期当天或已过期时返回空值。')
            s['sample'] = {'in': '计划完成日期（假设今天为2026-04-17）', 'inType': 'date', 'out': s['label'], 'rows': [['2026-05-15', 28], ['2026-04-10', '']]}
        if key == 'cvBmr':
            s['desc'] = '按 Mifflin–St Jeor 公式估算基础代谢率。体重单位 kg、身高 cm、年龄周岁，输出 kcal/天，四舍五入保留整数。'
        s.update(local=True, formula=FORMULAS[key], formulaVersion=1)
        shown = FORMULAS[key]
        for role in s['inputRoles']:
            shown = shown.replace('[' + role['key'] + ']', '[' + role['label'] + ']')
        s['formulaDisplay'] = shown


def calculate(key, cfg, record, scene):
    bindings = cfg.get('inputBindings') or {}
    inputs = cfg.get('inputFields') or []
    row = {}
    for index, role in enumerate(scene['inputRoles']):
        name = bindings.get(role['key']) if bindings else inputs[index] if index < len(inputs) else None
        value = record.get(name)
        if value is None or value == '':
            if 'date' in role['types'] and key not in ('fnVat', 'cvMonthEnd', 'cvMonthDays', 'workdays', 'stHours', 'pdTicketTime'):
                row[role['key']] = None
                continue
            return None
        if 'date' in role['types']:
            try:
                from .ai_local import _date
                parsed = _date(value)
                if parsed is None:
                    raise ValueError('invalid date')
                row[role['key']] = parsed if key in ('stHours', 'pdTicketTime') else parsed.date()
            except ValueError:
                raise ValueError(f"{role['label']}必须是有效日期")
        elif role['key'] in ('gender', 'text'):
            row[role['key']] = value
        else:
            try:
                number = float(str(value).replace(',', '').strip())
            except (ValueError, TypeError):
                raise ValueError(f"{role['label']}必须是纯数字，请重新绑定输入字段")
            if isinstance(value, bool) or not math.isfinite(number) or (key in CONTRACTS and number < 0):
                raise ValueError(f"{role['label']}必须是有效的非负数")
            row[role['key']] = number
    # Validate inputs; the result itself is computed only by the formula below.
    if key == 'cvBmi' and (row['height'] <= 0 or row['weight'] <= 0):
        raise ValueError('身高和体重必须大于0')
    if key in ('pdDefect', 'pdHours', 'stAttendance'):
        a, b = row['value'], row['total']
        if a < 0 or b < 0 or (b == 0 and key != 'pdHours'):
            raise ValueError('数量不能为负，作为分母的总数必须大于0')
        if key == 'pdDefect' and a > b:
            raise ValueError('不良数不能大于批次总数')
    if key in ('stHours', 'pdTicketTime'):
        for role in ('start', 'end'):
            if row[role].tzinfo is None:
                row[role] = row[role].replace(tzinfo=timezone(timedelta(hours=8)))
    if key in ('stHours', 'pdTicketTime', 'orderShippingStatus') and row.get('start') and row.get('end') and row['end'] < row['start']:
        raise ValueError('结束/发货时间不能早于开始/下单时间')
    result = expr.evaluate(expr.parse(FORMULAS[key], set(row)), row, strict=True)
    return result.isoformat()[:10] if isinstance(result, (date, datetime)) else None if result == '' else result
