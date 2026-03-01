from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.crawl import router as crawl_router
from app.routers.query import router as query_router
from app.routers.jobs import router as jobs_router
from app.routers.stream import router as stream_router
from app.services.mongodb import close_db, ensure_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    yield
    await close_db()


app = FastAPI(title="Hoff", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crawl_router)
app.include_router(query_router)
app.include_router(jobs_router)
app.include_router(stream_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
