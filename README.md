# 通用数据记录工具

Excel 驱动的轻量级数据管理系统：上传 Excel → AI 分析结构 → 确认后自动建表导入 → 动态生成增删改查界面。方案设计见 [docs/方案设计.md](docs/方案设计.md)。

## 快速开始

### 后端（FastAPI）

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

默认使用 SQLite（零配置）。局域网部署切 MySQL：复制 `.env.example` 为 `.env`，设置 `GRT_DATABASE_URL`。

### 前端（Vue3 + Element Plus）

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 （dev 模式下 `/api` 自动代理到 8000 端口）。

### 生产部署

前端 `npm run build` 后，后端会自动托管 `frontend/dist`，只需启动后端即可。

## 使用流程

1. **模型设置**：先添加一个大模型服务（DeepSeek / 通义千问等 OpenAI 兼容接口，或 Claude），点"测试"确认连通，设为默认。
2. **导入 Excel**：上传文件 → 选择工作表和表头行 → AI 分析结构 → 确认/调整字段（类型、控件、必填）→ 建表并导入。
3. **数据管理**：在"数据表"里打开表，使用自动生成的列表筛选、新增、编辑、删除。

## 目录结构

```
backend/
  app/
    routers/      # API 路由（excel/tables/dyn/settings）
    services/     # excel_parser / typemap / meta_service / dyn_engine / uploads / llm/
    models.py     # 元数据表（meta_tables/meta_fields/import_batches/llm_providers/audit_logs）
frontend/
  src/views/      # TableList / ImportWizard / DynamicTable / Settings
  src/components/ # DynamicForm（元数据驱动的动态表单）
docs/方案设计.md
```
