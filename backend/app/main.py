from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, SessionLocal, engine
from .routers import auth, dyn, excel, friends, groups, notify, rbac, reports, settings as settings_router, share_links, shares, tables, tasks, users, vision
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
    yield
    scheduler.shutdown()


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

# 其余所有接口都需要登录（支持 Authorization 头或 ?token= 查询参数，后者供导出下载用）
protected = [Depends(get_current_user)]
app.include_router(users.router, dependencies=protected)
app.include_router(rbac.router, dependencies=protected)
app.include_router(groups.router, dependencies=protected)
app.include_router(excel.router, dependencies=protected)
app.include_router(tables.router, dependencies=protected)
app.include_router(dyn.router, dependencies=protected)
app.include_router(vision.router, dependencies=protected)
app.include_router(tasks.router, dependencies=protected)
app.include_router(reports.router, dependencies=protected)
app.include_router(notify.router, dependencies=protected)
app.include_router(friends.router, dependencies=protected)
app.include_router(shares.router, dependencies=protected)
app.include_router(settings_router.router, dependencies=protected)

# 前端构建产物存在时直接由后端托管（生产模式）
dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="static")
