"""请求体模型（响应统一用 dict 构造，保持轻量）。"""
import re

from pydantic import BaseModel, field_validator

from .services.typemap import DATA_TYPES, WIDGETS

FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


class AnalyzeRequest(BaseModel):
    file_id: str
    sheet_name: str
    header_row: int = 1


class FieldIn(BaseModel):
    source_header: str | None = None
    field_name: str
    label: str
    data_type: str = "varchar"
    length: int = 255
    nullable: bool = True
    default_value: str | None = None
    widget: str = "input"
    options: dict = {}

    @field_validator("field_name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not FIELD_NAME_RE.match(v):
            raise ValueError("字段名必须是小写字母开头的 snake_case（a-z、0-9、_，最长41字符）")
        return v

    @field_validator("data_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in DATA_TYPES:
            raise ValueError(f"不支持的字段类型：{v}")
        return v

    @field_validator("widget")
    @classmethod
    def _check_widget(cls, v: str) -> str:
        if v not in WIDGETS:
            raise ValueError(f"不支持的控件类型：{v}")
        return v


class SourceIn(BaseModel):
    file_id: str
    sheet_name: str
    header_row: int = 1


class TableCreate(BaseModel):
    label: str
    name: str | None = None          # 表名，留空自动生成 dyn_xxx（json 模式下为逻辑名，不建物理表）
    fields: list[FieldIn]
    source: SourceIn | None = None   # 有 source 则建表后导入数据
    storage_mode: str = "json"       # json（默认，单表存储）/ physical（独立物理表，仅 vip/admin）

    @field_validator("storage_mode")
    @classmethod
    def _check_storage(cls, v: str) -> str:
        if v not in ("json", "physical"):
            raise ValueError("storage_mode 必须是 json 或 physical")
        return v


class TableShareIn(BaseModel):
    user_id: int | None = None       # 分享给用户（优先，选择器选中后直传 id）
    username: str | None = None      # 分享给用户（二选一，user_id 的兜底）
    group_id: int | None = None      # 分享给用户组（二选一）
    can_view: bool = True
    can_create: bool = False
    can_edit: bool = False
    can_delete: bool = False


class FriendRequestIn(BaseModel):
    username: str


class FieldUpdate(BaseModel):
    """只允许修改展示类属性，物理结构变更（改名/改类型/删列）另行设计迁移流程"""
    id: int
    label: str | None = None
    nullable: bool | None = None
    widget: str | None = None
    options: dict | None = None
    sort_order: int | None = None


class TableUpdate(BaseModel):
    label: str | None = None
    fields: list[FieldUpdate] | None = None


class ProviderIn(BaseModel):
    name: str
    type: str = "openai_compat"      # openai_compat / claude
    base_url: str | None = None
    api_key: str | None = None       # 更新时留空表示不修改
    model: str
    vision_model: str | None = None
    is_default: bool = False
    enabled: bool = True

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in ("openai_compat", "claude"):
            raise ValueError("type 只能是 openai_compat 或 claude")
        return v


class TaskRuleIn(BaseModel):
    name: str
    table_id: int
    enabled: bool = False
    condition_mode: str = "structured"          # structured / llm
    condition: dict = {}
    schedule: dict = {}                          # {type: interval, minutes} | {type: cron, expr}
    action: dict = {}                            # {type, template, webhook_url?, recipients}
    cooldown_hours: int = 24
    max_per_run: int = 100

    @field_validator("condition_mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        if v not in ("structured", "llm"):
            raise ValueError("condition_mode 只能是 structured 或 llm")
        return v

    @field_validator("cooldown_hours", "max_per_run")
    @classmethod
    def _check_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("不能为负数")
        return v


class ReportTemplateIn(BaseModel):
    name: str
    description: str | None = None
    table_id: int
    enabled: bool = False
    range: dict = {}       # {mode, date_field, start?, end?}
    blocks: list[dict] = []
    filter_fields: list[str] = []   # 查看端开放自助筛选的字段
    schedule: dict = {}    # {type: interval, minutes} | {type: cron, expr}
    push: dict = {}        # {recipients, formats, subject}


class WorkflowIn(BaseModel):
    name: str
    description: str = ""
    enabled: bool = False
    trigger: dict = {}     # {type: schedule|record_created|record_updated|webhook|manual, ...}
    nodes: list[dict] = [] # [{id, type, name?, config, on_error?}]
    edges: list[dict] = [] # [{from, to, branch?}]
