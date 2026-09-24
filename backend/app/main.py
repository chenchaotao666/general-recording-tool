from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, SessionLocal, engine
from .routers import assistant, auth, dyn, excel, friends, groups, images, mcp, notes, notify, rbac, reports, settings as settings_router, share_links, shares, tables, tasks, users, vision, workflows
from .services import scheduler
from .services.migrate import run_migrations
from .utils.auth import get_current_user, hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _seed_admin()
    run_migrations(engine)
    scheduler.start()
    _cleanup_orphan_images()
    yield
    scheduler.shutdown()


def _cleanup_orphan_images():
    """启动时清理超期未关联记录的临时图片（上传后没保存进任何记录的）。"""
    try:
        from .services.images import cleanup_orphans
        n = cleanup_orphans(SessionLocal())
        if n:
            print(f"[images] 清理孤儿图片 {n} 张", flush=True)
    except Exception:  # noqa: BLE001 — 清理失败不影响启动
        pass


def _seed_admin():
    """首次启动（无用户时）创建默认管理员，登录后请尽快修改密码"""
    from .models import User

    db = SessionLocal()
    try:
        if not db.query(User).first():
            db.add(User(username="admin", password_hash=hash_password("admin123"), role="admin"))
            db.commit()
    finally:
        db.close()


app = FastAPI(title="通用数据记录工具", lifespan=lifespan)

# 局域网部署，放开跨域；前端 dev server 通过 vite proxy 访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)  # 登录接口本身不鉴权
app.include_router(share_links.router)  # 管理端点自带 get_current_user；/share/{token} 公开免登录
app.include_router(workflows.public_router)  # webhook 触发：URL 即凭证，免登录
app.include_router(mcp.public_router)        # MCP 端点：URL 路径 token 即凭证，免登录

# 其余所有接口都需要登录（支持 Authorization 头或 ?token= 查询参数，后者供导出下载用）
protected = [Depends(get_current_user)]
app.include_router(users.router, dependencies=protected)
app.include_router(images.router, dependencies=protected)
app.include_router(rbac.router, dependencies=protected)
app.include_router(groups.router, dependencies=protected)
app.include_router(excel.router, dependencies=protected)
app.include_router(tables.router, dependencies=protected)
app.include_router(dyn.router, dependencies=protected)
app.include_router(vision.router, dependencies=protected)
app.include_router(tasks.router, dependencies=protected)
app.include_router(workflows.router, dependencies=protected)
app.include_router(workflows.templates_router, dependencies=protected)
app.include_router(mcp.router, dependencies=protected)
app.include_router(reports.router, dependencies=protected)
app.include_router(assistant.router, dependencies=protected)
app.include_router(notes.router, dependencies=protected)
app.include_router(notify.router, dependencies=protected)
app.include_router(friends.router, dependencies=protected)
app.include_router(shares.router, dependencies=protected)
app.include_router(settings_router.router, dependencies=protected)

# 前端构建产物存在时直接由后端托管（生产模式）
dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if dist.exists():
    from starlette.responses import FileResponse
    from starlette.staticfiles import StaticFiles

    class NoCacheStaticFiles(StaticFiles):
        """index.html 不带哈希、内容随构建变化，必须禁用缓存；assets 带哈希可长缓存。"""

        async def get_response(self, path, scope):
            resp = await super().get_response(path, scope)
            if isinstance(resp, FileResponse) and resp.path.endswith("index.html"):
                resp.headers["Cache-Control"] = "no-cache, must-revalidate"
            return resp

    app.mount("/", NoCacheStaticFiles(directory=dist, html=True), name="static")
