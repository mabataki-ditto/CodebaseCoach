import asyncio
import json
import logging
from threading import Thread

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.workflow import require_llm_configuration
from app.schemas.agent import AnalyzeRepoRequest, AnalyzeRepoResponse
from app.core.errors import AppError
from app.schemas.analysis_job import (
    AnalysisJobCancelResponse,
    AnalysisJobCreateResponse,
    AnalysisJobResumeResponse,
    AnalysisJobResumeStatusResponse,
    AnalysisJobSnapshot,
)
from app.services.analysis_job_service import AnalysisJobService, analysis_job_service
from app.services.analysis_execution_service import analysis_execution_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


def run_codebase_analysis_workflow(repo_url: str) -> AnalyzeRepoResponse:
    """Compatibility seam retained for API tests and legacy callers."""
    return analysis_execution_service.run_sync(repo_url)


def run_codebase_analysis_job(
    *, job_id: str, repo_url: str, job_service: AnalysisJobService
) -> None:
    """Compatibility seam retained while the execution service owns routing."""
    analysis_execution_service.run_job(
        job_id=job_id,
        repo_url=repo_url,
        job_service=job_service,
    )


@router.post("/analyze", response_model=AnalyzeRepoResponse)
def analyze_repo(request: AnalyzeRepoRequest) -> AnalyzeRepoResponse:
    logger.info("[analyze] received request | repo_url=%s | mode=real", request.repo_url)
    return run_codebase_analysis_workflow(request.repo_url)


@router.post("/analyze/jobs", response_model=AnalysisJobCreateResponse)
def create_analysis_job(request: AnalyzeRepoRequest) -> AnalysisJobCreateResponse:
    require_llm_configuration()
    job = analysis_job_service.create_job(request.repo_url)
    thread = Thread(
        target=run_codebase_analysis_job,
        kwargs={
            "job_id": job.id,
            "repo_url": request.repo_url,
            "job_service": analysis_job_service,
        },
        daemon=True,
    )
    thread.start()
    logger.info("[analyze-job] created | job_id=%s | repo_url=%s", job.id, request.repo_url)
    return AnalysisJobCreateResponse(job_id=job.id, status=job.status)


@router.get("/analyze/jobs/{job_id}", response_model=AnalysisJobSnapshot)
def get_analysis_job(job_id: str) -> AnalysisJobSnapshot:
    return analysis_job_service.get_snapshot(job_id)


@router.get(
    "/analyze/jobs/{job_id}/resume-status",
    response_model=AnalysisJobResumeStatusResponse,
)
def get_analysis_job_resume_status(job_id: str) -> AnalysisJobResumeStatusResponse:
    return analysis_execution_service.get_resume_status(job_id, analysis_job_service)


@router.post(
    "/analyze/jobs/{job_id}/resume",
    response_model=AnalysisJobResumeResponse,
)
def resume_analysis_job(job_id: str) -> AnalysisJobResumeResponse:
    response = analysis_execution_service.resume_job(job_id, analysis_job_service)
    job = analysis_job_service.get_job(job_id)
    thread = Thread(
        target=run_codebase_analysis_job,
        kwargs={
            "job_id": job.id,
            "repo_url": job.repo_url,
            "job_service": analysis_job_service,
        },
        daemon=True,
    )
    try:
        thread.start()
    except Exception as error:
        analysis_job_service.update_status(
            job.id,
            "failed",
            error_message="恢复任务后台线程启动失败",
        )
        raise AppError(
            status_code=500,
            code="ANALYSIS_JOB_RESUME_START_FAILED",
            message="恢复任务启动失败",
            detail=str(error) or None,
        ) from error
    logger.info(
        "[analyze-job] resume requested | job_id=%s | recovery_mode=%s",
        job.id,
        response.recovery_mode,
    )
    return response


@router.get("/analyze/jobs/{job_id}/events")
async def stream_analysis_job_events(job_id: str, after: int = 0) -> StreamingResponse:
    analysis_job_service.get_job(job_id)

    async def event_generator():
        sequence = max(after, 0)
        while True:
            events = analysis_job_service.get_events_after(job_id, sequence)
            for event in events:
                sequence = event.sequence
                if event.type in {"job_completed", "job_failed", "job_cancelled"}:
                    current_status = analysis_job_service.get_job(job_id).status
                    if not _terminal_event_matches_status(event.type, current_status):
                        continue
                yield _format_sse_event(event.type, event.sequence, event.model_dump())
                if event.type in {"job_completed", "job_failed", "job_cancelled"}:
                    return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/analyze/jobs/{job_id}/cancel", response_model=AnalysisJobCancelResponse)
def cancel_analysis_job(job_id: str) -> AnalysisJobCancelResponse:
    job = analysis_job_service.request_cancel(job_id)
    logger.info("[analyze-job] cancel requested | job_id=%s", job_id)
    return AnalysisJobCancelResponse(job_id=job.id, status=job.status)


def _format_sse_event(event_type: str, event_id: int, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"id: {event_id}\nevent: {event_type}\ndata: {payload}\n\n"


def _terminal_event_matches_status(event_type: str, status: str) -> bool:
    return {
        "job_completed": "success",
        "job_failed": "failed",
        "job_cancelled": "cancelled",
    }.get(event_type) == status
