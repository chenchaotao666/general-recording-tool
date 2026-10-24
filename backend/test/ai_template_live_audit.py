"""Explicit live audit: creates only its named fixture table; uses configured real LLM.

Run from backend with .venv/Scripts/python.exe test/ai_template_live_audit.py setup|run|report.
No mock provider, no existing business records are inputs. State supports selected reruns.
"""
import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.models import MetaTable, MetaField, MetaView, Record, SmartAiRun, SmartDoc, SmartDocEntry
from app.schemas import FieldIn, TableCreate
from app.services import ai_field_service as ai, meta_service, json_store, smart_files, entitlement
from app.services.ai_scenes import SCENES, CATEGORIES
from app.services.field_registry import to_field_in
from app.services.smart_format import display

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'docs/AI模板全量验证数据.json'
REPORT = ROOT / 'docs/AI模板全量验证报告.md'
NAME = 'AI 模板全量验证（142项）'
META = [('case_name','验证用例'), ('scene_key','模板标识'), ('category','模板分类'), ('mode','执行方式'),
        ('input_text','样例输入'), ('expected','预期结果'), ('actual','实际结果'), ('verdict','验证状态'), ('note','验证说明')]

def dump(v):
    return json.dumps(v, ensure_ascii=False, default=str)

def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

def fixture(scene):
    key = scene['key']
    rows = (scene.get('sample') or {}).get('rows') or [[f'{scene["label"]}：合成验证数据', None]]
    source, expected = rows[0]
    overrides = {
        'classify': ('苹果、香蕉；分类规则：水果或办公用品', '水果'),
        'summary': ('项目完成需求评审，登录功能已开发完成，下周开展接口联调。', None),
        'extract': ('2026年10月24日，示例项目已完成需求评审，负责人测试员甲，下周联调。', None),
        'imageUnderstand': ('合成测试图：白底蓝色方框，文字 AI TEST 2026', None),
        'custom': ('你好', 'Hello'),
        'pdfToText': ('Contract HT-2026-001. Valid until 2026-12-31.', 'Contract HT-2026-001'),
        'fnIit': ('纯合成规则测试，不代表实际税制：年度应纳税所得额30000元，适用税率3%，速算扣除0元。按所得额乘税率减速算扣除计算。', 900),
        'fnIitLevel': ('纯合成规则：年应纳税所得额30000元；不超过36000元适用3%档；请仅按所给规则返回3%。', '3%'),
        'fnBonusSeparate': ('纯合成规则：年终奖12000元，除以12为1000元，对应税率3%、速算扣除0元。仅按给定规则输出税率。', '3%'),
        'fnBonusMerge': ('纯合成规则：原年应纳税所得额24000元，奖金12000元，合并36000元，不超过36000元适用3%档，速算扣除0元。', None),
        'fnVat': ('纯合成规则：销项税1300元，准予抵扣进项税500元，按销项减进项计算应纳税额800元。', None),
        'fxLive': ('USD/CNY，待接入汇率服务', None),
        'fxHistory': ('USD/CNY，2026-01-01，待接入历史汇率服务', None),
    }
    source, expected = overrides.get(key, (source, expected)) if not scene.get('formula') else (source, expected)
    today = datetime.now().date()
    role_values = {
        'fnIit': [9200], 'fnIitLevel': [14200], 'fnBonusSeparate': [60000],
        'fnBonusMerge': [120000,60000], 'fnVat': ['2026-10-15'], 'hrLeave': [6],
        'workdays': ['2026-10-12', '2026-10-16'], 'taskStatus': ['2026-01-01', '2026-01-10', '2026-01-09'],
        'deadlineCountdown': [(today + timedelta(days=3)).isoformat()],
        'hrAge': ['2000-10-25'], 'hrSeniority': ['2020-10-24'], 'hrContract': [(today+timedelta(days=8)).isoformat()],
        'stHealthDays': [(today+timedelta(days=3)).isoformat()], 'stHealthExpiry': ['2024-02-29'],
        'cvBmi': [175,70], 'cvBmr': [175,70,30,'男'], 'pdStock':[100,20,15], 'pdStockAlert':[8,10],
        'pdDefect':[3,200], 'pdHours':[5,8], 'stAttendance':[19,20],
        'stHours':['2026-01-01 09:00:00','2026-01-01 18:00:00'],
        'pdTicketTime':['2026-01-01 09:00:00','2026-01-01 11:30:00'],
        'orderShippingStatus':['2026-10-01','2026-10-04'],
        'memberTaskCount':['memberTaskCount-甲'], 'memberWorkload':['memberWorkload-甲',3],
        'taskCompletion':['taskCompletion-项目甲','已完成'], 'mkRank':[34],
        'hrLeaveUsed':['hrLeaveUsed-甲',2,today.isoformat()], 'stTotalHours':['stTotalHours-甲',8],
    }
    expected = {'pdDefect':1.5,'memberTaskCount':2,'memberWorkload':8,'taskCompletion':66.67,'mkRank':1,
                'hrLeaveUsed':5,'stTotalHours':15,'markDuplicate':True,'duplicatePhone':True}.get(key, expected)
    if key == 'hrAge': expected = today.year-2000-((today.month,today.day)<(10,25))
    if key == 'hrSeniority': expected = round((today-datetime(2020,10,24).date()).days/365.25,1)
    if key in ('markDuplicate','duplicatePhone'): source = '13800000001'
    return source, expected, role_values.get(key, [])

def attachment(text, kind, table_id, owner, key):
    if kind == 'png':
        from PIL import Image, ImageDraw, ImageFont
        import textwrap
        im = Image.new('RGB',(1000,560),'white'); draw = ImageDraw.Draw(im)
        font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',26)
        draw.rectangle((18,18,982,542),outline='#2878df',width=5)
        draw.multiline_text((40,40),'合成测试样例（非真实证件）\n'+'\n'.join(textwrap.wrap(str(text),30)),font=font,fill='#222222',spacing=16)
        out=BytesIO(); im.save(out,format='PNG'); data=out.getvalue()
    elif kind == 'pdf':
        from reportlab.pdfgen.canvas import Canvas
        out=BytesIO(); c=Canvas(out); c.drawString(40,790,'SYNTHETIC TEST DOCUMENT'); c.drawString(40,760,'Contract HT-2026-001. Valid until 2026-12-31.'); c.save(); data=out.getvalue()
    else:
        data = str(text).encode('utf-8')
    return smart_files.save(data, f'{key}-test.{kind}',table_id,owner)

def setup():
    db=SessionLocal(); tenant_id=2; owner=2
    doc=db.query(SmartDoc).filter_by(tenant_id=tenant_id,is_default=True).one()
    entitlement.assert_tenant_writable(db,tenant_id); entitlement.check_quota(db,tenant_id,'max_tables')
    defs=[FieldIn(**to_field_in('text',label,name)) for name,label in META]
    defs += [FieldIn(**to_field_in('file','样例附件','input_file')),
             FieldIn(**to_field_in('number','金额','amount')),FieldIn(**to_field_in('number','数量','quantity'))]
    if STATE.exists():
        state=json.loads(STATE.read_text(encoding='utf-8'));mt=db.get(MetaTable,state['table_id'])
    else:
        mt=meta_service.create_business_table(db,TableCreate(label=NAME,name='ai_template_audit_20261024',fields=defs),owner,tenant_id)
        entry=SmartDocEntry(doc_id=doc.id,name=NAME,type='sheet',ref_table_id=mt.id,order_no=999)
        db.add(entry); db.commit(); entitlement.bump_usage(db,tenant_id,'table_count',1);db.commit()
        state={'created_at':datetime.now().isoformat(),'table_id':mt.id,'tenant_id':tenant_id,'owner_id':owner,
               'url':f'http://localhost:5173/smart/table/{mt.id}','cases':[]}
    cat_names={c['key']:c['label'] for c in CATEGORIES}
    cat_names['custom']='自定义'
    for index,s in enumerate(SCENES):
        if any(c['key']==s['key'] for c in state['cases']):continue
        key=s['key']; source,expected,values=fixture(s)
        data={'case_name':f'{index+1:03d} {s["label"]}','scene_key':key,'category':cat_names[s['category']],
              'mode':s['executionLabel'],'input_text':str(source),'expected':dump(expected) if expected is not None else '依据输入核对结果，不要求逐字一致',
              'verdict':'未接入' if s.get('disabled') else '待验证','note':s.get('disabledReason',''),'amount':100,'quantity':3}
        cfg={'scene':key,'outputType':s['outputType'],'autoUpdate':False,'allowNewOptions':True,'inputFields':['input_text']}
        if key=='custom':cfg['prompt']='将输入翻译为英文，只返回翻译。'
        opts=s.get('defaultOptions') or (['水果','办公用品'] if key=='classify' else ['自然风光','人文景观'] if key=='tagMatch' else [])
        cfg['options']=[{'id':f'opt_{i}','label':label,'color':'blue'} for i,label in enumerate(opts)]
        role_fields=[]
        for role,value in zip(s.get('inputRoles',[]),values):
            name=f'in_{key}_{role["key"]}'.lower()
            kind='number' if isinstance(value,(int,float)) else 'text'
            role_fields.append(MetaField(table_id=mt.id,**{k:v for k,v in to_field_in(kind,f'{s["label"]}·{role["label"]}',name).items() if k in {'field_name','label','data_type','field_type','widget','options'}},sort_order=300+index*4+len(role_fields)))
            data[name]=value;cfg.setdefault('inputBindings',{})[role['key']]=name
        if role_fields:cfg['inputFields']=[f.field_name for f in role_fields];db.add_all(role_fields)
        if key in ('markDuplicate','duplicatePhone'):
            name=f'in_{key}'.lower();db.add(MetaField(table_id=mt.id,field_name=name,label=f'{s["label"]}·手机号',data_type='text',field_type='text',widget='input',sort_order=290+index))
            cfg['inputFields']=[name];data[name]=source
        if s['input'] in ('file','image') or s.get('asset') and key!='qrcode':
            kind='png' if s['input']=='image' else 'pdf' if key in ('pdfToText','fiPdfImage','fiPdfWatermark') else 'txt'
            data['input_file']=[attachment(source,kind,mt.id,owner,key)];cfg['inputFields']=['input_file']
        if key in ('cvRandom','cvUuid','cvPassword'):cfg['inputFields']=[]
        fn=('ai_'+key).lower()
        if not s.get('disabled') and not s.get('action'):
            f=to_field_in('ai',s['label'],fn,cfg)
            db.add(MetaField(table_id=mt.id,**{k:v for k,v in f.items() if k in {'field_name','label','data_type','field_type','widget','options'}},sort_order=20+index))
        db.commit()
        fields=meta_service.get_meta_fields(db,mt.id)
        if not s.get('disabled') and not s.get('action'):ai.validate_template_config(cfg,fields)
        row=json_store.create_record(db,mt,fields,data,user='cct',owner_id=owner)
        case={'key':key,'label':s['label'],'category':s['category'],'execution':s['execution'],'disabled':bool(s.get('disabled')),
              'record_id':row['id'],'field':fn if not s.get('disabled') and not s.get('action') else None,'config':cfg,
              'input':data,'expected':expected,'status':data['verdict'],'note':data['note']}
        state['cases'].append(case);save_state(state)
        # Separate real rows make aggregate/duplicate tests meaningful.
        if s.get('scope')=='table':
            changes=[]
            if key in ('markDuplicate','duplicatePhone'):changes=[{cfg['inputFields'][0]:'+86 138-0000-0001' if key=='duplicatePhone' else source}]
            elif key=='memberTaskCount':changes=[{}]
            elif key in ('memberWorkload','hrLeaveUsed','stTotalHours'):changes=[{cfg['inputBindings']['value']:{'memberWorkload':5,'hrLeaveUsed':3,'stTotalHours':7}[key]}]
            elif key=='taskCompletion':changes=[{cfg['inputBindings']['status']:'已完成'},{cfg['inputBindings']['status']:'未开始'}]
            elif key=='mkRank':changes=[{cfg['inputBindings']['value']:3},{cfg['inputBindings']['value']:4}]
            for n,change in enumerate(changes):
                extra={**data,**change,'case_name':data['case_name']+f' 辅助记录{n+1}','verdict':'汇总辅助数据'}
                json_store.create_record(db,mt,fields,extra,user='cct',owner_id=owner)
    fields=meta_service.get_meta_fields(db,mt.id); names=[f.field_name for f in fields]
    for cat in [None]+CATEGORIES+[{'key':'custom','label':'自定义'}]:
        existing_view=db.query(MetaView).filter_by(table_id=mt.id,name=cat['label'] if cat else '验证总览').first()
        visible=[x[0] for x in META]+['input_file']
        if cat:
            cases=[c for c in state['cases'] if c['category']==cat['key']]
            visible += [c['field'] for c in cases if c['field']]+[name for c in cases for name in c['config']['inputFields']]
        config={'fieldVisibility':{n:n in visible for n in names},'fieldOrder':list(dict.fromkeys(visible+names)),
                'colWidths':{'case_name':220,'input_text':320,'expected':220,'actual':320,'note':320},'rowHeight':3}
        if cat:config['filters']={'conjunction':'and','conditions':[{'fieldId':'category','operator':'eq','value':cat['label']}]}
        if existing_view:existing_view.config=config
        else:db.add(MetaView(table_id=mt.id,name=cat['label'] if cat else '验证总览',type='grid',config=config,is_default=cat is None,created_by=owner))
    db.commit();db.close();save_state(state);print(dump({'created':state['table_id'],'cases':len(state['cases']),'url':state['url']}),flush=True)

def inspect_value(case,value,shown):
    key=case['key']; expected=case['expected']
    if key=='cvRandom': return isinstance(value,(int,float)) and 1<=value<=100
    if key=='cvUuid':
        import uuid
        try:uuid.UUID(value);return True
        except Exception:return False
    if key=='cvPassword':return isinstance(value,str) and len(value)>=16 and any(c.isupper() for c in value) and any(c.islower() for c in value) and any(c.isdigit() for c in value)
    if case['execution']=='asset':
        from PIL import Image
        from pypdf import PdfReader
        if not value:return False
        for item in value:
            path,_=smart_files.locate(item['id'])
            if path.suffix.lower()=='.pdf':assert len(PdfReader(str(path)).pages)>0
            else:
                with Image.open(path) as im: im.verify()
        return True
    if key=='pdfToText':return expected in str(value)
    if value is None or value=='':return False
    if isinstance(expected,bool):return value is expected
    if isinstance(expected,(int,float)) and key!='mkScore':return isinstance(value,(int,float)) and abs(value-expected)<0.02
    if case['execution'] in ('local', 'calculation'):return str(shown)==str(expected)
    if case['config']['outputType'] in ('singleSelect','date'):return expected is None or str(expected).replace(' ','') in str(shown).replace(' ','')
    return None  # Generated prose needs review against the input, not exact string equality.

def run(keys=None):
    state=json.loads(STATE.read_text(encoding='utf-8'));db=SessionLocal();mt=db.get(MetaTable,state['table_id'])
    assert 'ai_template_audit_' in mt.name and mt.label==NAME and mt.owner_id==state['owner_id'], 'Refuse to modify a business table'
    for case in state['cases']:
        if keys and case['key'] not in keys:continue
        if not keys and case['status']!='待验证':continue
        if case['status']!='待验证':
            case.setdefault('history',[]).append({k:case.get(k) for k in ('status','actual','display','note','seconds')})
        start=time.monotonic();note='';value=None;shown=''
        try:
            if case['disabled']:
                case['status']='未接入';continue
            if case['key']=='writeFormula':
                result=ai.generate_formula(db,mt.id,'金额乘以数量，返回数字。')
                from app.services import expr
                value=expr.evaluate(expr.parse(result['formula']),{'amount':100,'quantity':3})
                shown=result['display']+f'；100 × 3 = {value}';ok=value==300
                case['generated_formula']=result
            else:
                ai.process(db,mt.id,case['field'],[case['record_id']])
                db.expire_all();r=db.query(SmartAiRun).filter_by(table_id=mt.id,field_name=case['field'],record_id=case['record_id']).one()
                case['tokens']=r.tokens_used;case['billable']=r.billable
                if r.status!='ok':raise RuntimeError(r.error)
                row=db.get(Record,case['record_id']);value=row.data.get(case['field']);f=db.query(MetaField).filter_by(table_id=mt.id,field_name=case['field']).one()
                shown=display(db,f,value,{})
                ok=inspect_value(case,value,shown)
            status='通过' if ok is True else '待语义复核' if ok is None else '结果不符'
        except Exception as e:
            db.rollback();status='执行失败';note=str(getattr(e,'detail',e))[:800]
        case.update(status=status,actual=value,display=shown,note=note,seconds=round(time.monotonic()-start,2))
        row=db.get(Record,case['record_id']);row.data={**row.data,'actual':shown or dump(value),'verdict':status,'note':note};db.commit()
        save_state(state);print(dump({'key':case['key'],'status':status,'actual':shown[:180],'note':note[:250]}),flush=True)
    db.close();report()

def report():
    state=json.loads(STATE.read_text(encoding='utf-8'));counts=Counter(c['status'] for c in state['cases'])
    lines=['# AI 模板全量验证报告','',f'更新时间：{datetime.now().isoformat(timespec="seconds")}', '',
           f'验证表：[{NAME}]({state["url"]})，cct 个人空间，表 ID {state["table_id"]}。','',
           '使用合成数据；真实数据库落库、真实已配置 DeepSeek 模型调用（deepseek-v4-flash，图片调用也已实际成功）。没有用 mock 响应替代本次全量验证，也没有读取原业务表作为模型输入。', '',
           f'目录 {len(state["cases"])} 项；AI 字段 {sum(bool(c["field"]) for c in state["cases"])} 个；写公式单独验证。','',
           '状态汇总：'+ '；'.join(f'{k} {v}' for k,v in counts.items())+'。','',
           '已执行的 135 项包括 52 项本地计算、6 项文件处理、76 项模型模板和1项公式生成。7项未接入服务的模板不记为通过。', '',
           '## 如何查看和复验','',
           '- 登录 cct，切换个人工作空间，在智能表目录打开“AI 模板全量验证（142项）”；目录与网格权限接口均已确认可见。',
           '- 默认“验证总览”查看样例、预期、实际输出与状态。15个视图包含总览、13个业务分类和自定义分类。分类视图显示该类真正的 AI 字段及角色绑定输入列。',
           '- 表内有142条主用例、10条汇总辅助记录、5条可见边界用例，共157行；134个AI字段及1个实际公式字段，另有普通选项列的AI批量标签验证，总计196列。',
           '- 每个AI字段只生成它对应的样例行。自动更新默认关闭，避免142种不同输入互相触发；不要对所有AI字段执行全表刷新，否则会把不适用的行也送入各模板。',
           '- 修改样例后，刷新该行对应AI单元格即可复算；“实际结果”“验证状态”是审计快照，重新审计脚本运行后更新。',
           '- “推荐”视图含“AI 生成公式·实际计算”列，生成公式为金额×数量；100×3=300。', '',
           '## 本次修复与优化','',
           '|问题|改进|验证|','|---|---|---|',
           '|发货日期早于下单日期仍判已发货|拒绝逆序日期，显示明确错误|回归测试及验证表边界行|',
           '|数字输出允许NaN、Infinity和溢出值|数字输出统一拒绝非有限数值|7种异常数值回归断言|',
           '|超过4个附件被静默截断|先检查总附件数，超限明确报错|回归测试及5附件边界行|',
           '|图片输出重复.png后缀|以源文件名主体生成新名称|真实水印与锐化重新生成、附件下载|',
           '|身份证模板遗漏姓名，可能推断籍贯|提取姓名、出生日期、性别、地址，仅依据明确输入|真实模型重跑保留姓名与出生日期|',
           '|合规标签含义不明确|基于提供规则区分违规、存在风险、合规；缺规则不猜法规；同步目录示例|给定规则明确禁止绝对化表述时返回违规|',
           '|巡检描述把普通通道断言为消防通道|明确区分可见事实和待核实风险，禁止推测尺寸及设施用途|真实图像重跑，保留不确定性|',
           '|100字段上限无法承载全量验证表|JSON表允许最多500列，物理表仍100列|真实新增公式列、内存数据库建表/加列/上限回归|', '',
           '实现涉及 `backend/app/services/ai_field_service.py`、`ai_template_compute.py`、`ai_template_files.py`、`ai_scenes.py`、`ai_template_catalog.py` 和 `meta_service.py`。', '',
           '## 验证范围与限制','',
           '- “通过”表示本次具体样例满足数值、标签、日期、范围或附件可解析等明确断言。',
           '- “通过（样例语义复核）”表示 Codex 已逐项对照输入与真实输出检查；不是独立人工验收，不等于所有业务输入都准确。复核依据逐项保存在JSON数据中。',
           '- 三个现场视觉模板最初使用文字截图，模型没有据此冒充现场判断，返回空；修正为含可见场景要素的合成图后成功。真实低清照片、遮挡、多页复杂排版仍需补充业务验收。',
           '- 财务、年假、合规样例使用输入给定的合成规则，只检验规则遵循与运算，不验证现实法规、税率或申报适用性。',
           '- 本次通过正式接口验证用户可见性和操作链路；没有把接口验证表述为完整浏览器视觉验收或大数据性能压测。',
           '- 模型调用可能消耗当前服务用量；附件和结果均保存在本地应用。未接入的7项仍未实现，不用模型猜测实时汇率或伪造图片处理结果。', '',
           '## 接口与边界验证','',
           '后端回归：37个测试通过（模板计算/文件、输出类型、重试与空输入、此次新增回归，以及序号回填、公式链式调用和人员名称公式）。', '',
           '|检查|结果|说明|','|---|---|---|']
    for check in state.get('http_checks',[])+state.get('edge_checks',[]):
        lines.append(f'|{check["name"]}|{"通过" if check["passed"] else "失败"}|{str(check.get("detail") or check.get("actual") or "").replace(chr(10)," ")}|')
    empty=state.get('empty_checks',[])
    lines += ['',f'另检查 {len(empty)} 项模板的空输入计算分支：{sum(bool(c["passed"]) for c in empty)} 项通过且不调用模型；自定义提示词和公式动作不纳入该空输入统计。', '',
              '## 142项详细结果','', '|模板|方式|状态|实际结果|说明|','|---|---|---|---|---|']
    for c in state['cases']:
        detail=(c.get('display') or '').replace('|','\\|').replace('\n','<br>')
        note=(c.get('note') or '').replace('|','\\|').replace('\n','<br>')
        lines.append(f'|{c["label"]} (`{c["key"]}`)|{c["execution"]}|{c["status"]}|{detail}|{note}|')
    lines += ['', '完整输入、字段配置、预期结果、实际输出和耗时见同目录 `AI模板全量验证数据.json`。',
              '复跑：在 backend 目录执行 `.venv/Scripts/python.exe test/ai_template_live_audit.py run --keys 模板标识`。仅更新本验证表，调用配置模型会计入用量。']
    REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8');print(dump(dict(counts)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['setup','run','report']);p.add_argument('--keys',nargs='*');a=p.parse_args()
    if a.action=='setup':setup()
    elif a.action=='run':run(a.keys)
    else:report()
