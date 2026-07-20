from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent import router as agent_router
from app.api.docs import router as docs_router
from app.api.health import router as health_router
from app.api.history import router as history_router
from app.api.repo import router as repo_router
from app.core.config import settings
from app.core.errors import AppError, build_error_response


def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_response(exc).model_dump(),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="CodebaseCoach API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(repo_router)
    app.include_router(agent_router)
    app.include_router(history_router)
    app.include_router(docs_router)
    app.add_exception_handler(AppError, app_error_handler)
    return app


app = create_app()
