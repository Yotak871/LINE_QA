from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.models.database import init_db
from app.api.analyze import router as analyze_router
from app.api.share import router as share_router
from app.core.config import settings, UPLOAD_PATH


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="DesignSync API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(share_router)

# 업로드된 이미지를 정적 파일로 서빙
app.mount("/api/files", StaticFiles(directory=str(UPLOAD_PATH)), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok"}
