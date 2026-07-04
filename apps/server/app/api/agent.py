import asyncio
import json
import logging
from threading import Thread

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.workflow import require_llm_configuration, run_codebase_analysis_job, run_codebase_analysis_workflow
from app.schemas.agent import AnalyzeRepoRequest, AnalyzeRepoResponse
from app.schemas.analysis_job import AnalysisJobCancelResponse, AnalysisJobCreateResponse, AnalysisJobSnapshot
from app.services.analysis_job_service import analysis_job_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


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


@router.get("/analyze/jobs/{job_id}/events")
async def stream_analysis_job_events(job_id: str, after: int = 0) -> StreamingResponse:
    analysis_job_service.get_job(job_id)

    async def event_generator():
        sequence = max(after, 0)
        while True:
            events = analysis_job_service.get_events_after(job_id, sequence)
            for event in events:
                sequence = event.sequence
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
