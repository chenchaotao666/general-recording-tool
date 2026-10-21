import random
from datetime import date, timedelta
from sqlalchemy.orm import Session
from ..models import User

def _remap(obj, table_ids: dict[str, int]):
    """递归把 "$表key" 占位符替换为真实 table_id。"""
    if isinstance(obj, str) and obj.startswith("$") and obj[1:] in table_ids:
        return table_ids[obj[1:]]
    if isinstance(obj, dict):
        return {k: _remap(v, table_ids) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_remap(v, table_ids) for v in obj]
    return obj


# ---------- 示例数据 ----------

DEMO_DATA_COUNT = 50

_DEMO_NAMES = ["张伟", "王芳", "李娜", "刘洋", "陈杰", "杨静", "赵磊", "黄敏", "周涛", "吴倩"]
_DEMO_ITEMS = ["办公用品采购", "差旅费", "客户招待", "团队建设", "设备维修", "软件订阅", "快递费", "培训费", "市场推广", "日常采购"]
_DEMO_TEXTS = [
    "使用过程中整体顺畅，建议优化操作步骤",
    "响应速度有些慢，高峰期明显",
    "功能很实用，希望增加批量导出",
    "遇到一次数据不同步，请帮忙排查",
    "界面清晰，上手很快",
    "建议增加移动端支持",
]


def _demo_value(f, i: int):
    """按字段类型/控件/名称语义生成示例值。"""
    dt, w, label = f.data_type, f.widget, (f.label or f.field_name)
    if w == "select" and (f.options or {}).get("options"):
        opts = f.options["options"]
        return opts[i % len(opts)]
    if dt == "bool":
        return i % 2 == 0
    if dt == "int":
        return random.randint(1, 100)
    if dt == "decimal":
        return round(random.uniform(10, 2000), 2)
    if dt == "date":
        # 「到期/截止」类字段生成未来日期（到期提醒类模板才能筛出数据），其余生成近 60 天
        if any(k in label for k in ("到期", "截止")):
            return (date.today() + timedelta(days=random.randint(0, 60))).isoformat()
        return (date.today() - timedelta(days=random.randint(0, 60))).isoformat()
    if dt == "datetime":
        d = date.today() - timedelta(days=random.randint(0, 60))
        return f"{d.isoformat()} {random.randint(8, 20):02d}:{random.randint(0, 59):02d}"
    if any(k in label for k in ("申请人", "负责人", "客户", "姓名", "联系人", "销售", "业务员", "经手人")):
        return _DEMO_NAMES[i % len(_DEMO_NAMES)]
    if any(k in label for k in ("内容", "备注", "说明", "反馈")):
        return _DEMO_TEXTS[i % len(_DEMO_TEXTS)]
    if any(k in label for k in ("事项", "品名", "名称", "标题")):
        return _DEMO_ITEMS[i % len(_DEMO_ITEMS)]
    return f"{label}{i + 1}"


def _seed_demo_data(db: Session, table_id: int, user: User, count: int = DEMO_DATA_COUNT) -> int:
    """为新建的表生成示例数据（复用的已有表不动，避免污染真实数据）。"""
    from . import dyn_engine
    _, fields = dyn_engine.load_meta(db, table_id)
    for i in range(count):
        dyn_engine.create_record(db, table_id, {f.field_name: _demo_value(f, i) for f in fields},
                                 user=user.username)
    return count


