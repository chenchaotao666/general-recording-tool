from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from .routers import dyn, excel, notify, settings as settings_router, tables, tasks, vision
from .services import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="通用数据记录工具", lifespan=lifespan)

# 局域网部署，放开跨域；前端 dev server 通过 vite proxy 访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(excel.router)
app.include_router(tables.router)
app.include_router(dyn.router)
app.include_router(vision.router)
app.include_router(tasks.router)
app.include_router(notify.router)
app.include_router(settings_router.router)

# 前端构建产物存在时直接由后端托管（生产模式）
dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="static")
