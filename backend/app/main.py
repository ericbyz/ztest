"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize an empty local database without injecting seeded business data."""

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AI Test Tool API",
    version="0.1.0",
    description="需求驱动 API 自动化测试平台 MVP",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    """Describe the service root."""

    return {"name": "AI Test Tool API", "docs": "/docs"}
