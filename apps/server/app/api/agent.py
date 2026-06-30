from fastapi import APIRouter

from app.agent.workflow import run_codebase_analysis_workflow, run_mock_codebase_analysis_workflow
from app.schemas.agent import AnalyzeMockRequest, AnalyzeRepoRequest, AnalyzeRepoResponse

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/analyze", response_model=AnalyzeRepoResponse)
def analyze_repo(request: AnalyzeRepoRequest) -> AnalyzeRepoResponse:
    return run_codebase_analysis_workflow(request.repo_url)


@router.post("/analyze/mock", response_model=AnalyzeRepoResponse)
def analyze_repo_with_mock(request: AnalyzeMockRequest) -> AnalyzeRepoResponse:
    return run_mock_codebase_analysis_workflow(request.repo_url)
