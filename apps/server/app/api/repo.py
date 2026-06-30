from datetime import UTC, datetime
from time import perf_counter

from fastapi import APIRouter

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.metrics import RepoOperationMetrics
from app.schemas.repo import RepoParseResponse, RepoRequest, RepoScanResponse
from app.services.file_tree_service import build_file_tree, read_basic_files
from app.services.github_service import clone_repository
from app.services.metrics_service import count_file_tree_nodes, record_repo_operation_metrics
from app.services.repo_parser import parse_github_repo_url

router = APIRouter(prefix="/api/repo", tags=["repo"])


@router.post("/parse", response_model=RepoParseResponse)
def parse_repo(request: RepoRequest) -> RepoParseResponse:
    started_at = _now()
    started = perf_counter()
    try:
        parsed_repo = parse_github_repo_url(request.repo_url)
    except AppError as exc:
        _record_repo_metrics(
            RepoOperationMetrics(
                operation="repo_parse",
                status="failed",
                repo_url=request.repo_url,
                started_at=started_at,
                ended_at=_now(),
                duration_ms=_duration_ms(started),
                error_code=exc.code,
                error_message=exc.message,
            )
        )
        raise

    _record_repo_metrics(
        RepoOperationMetrics(
            operation="repo_parse",
            status="success",
            repo_url=parsed_repo.repo_url,
            owner=parsed_repo.owner,
            repo=parsed_repo.repo,
            started_at=started_at,
            ended_at=_now(),
            duration_ms=_duration_ms(started),
        )
    )
    return parsed_repo


@router.post("/scan", response_model=RepoScanResponse)
def scan_repo(request: RepoRequest) -> RepoScanResponse:
    started_at = _now()
    started = perf_counter()
    parsed_repo: RepoParseResponse | None = None
    try:
        parsed_repo = parse_github_repo_url(request.repo_url)
        local_path = clone_repository(parsed_repo, settings.temp_repo_path)
        file_tree = build_file_tree(
            local_path,
            max_depth=settings.max_file_tree_depth,
            max_entries=settings.max_file_tree_entries,
        )
        basic_files = read_basic_files(local_path, max_bytes=settings.max_basic_file_bytes)
    except AppError as exc:
        _record_repo_metrics(
            RepoOperationMetrics(
                operation="repo_scan",
                status="failed",
                repo_url=parsed_repo.repo_url if parsed_repo else request.repo_url,
                owner=parsed_repo.owner if parsed_repo else None,
                repo=parsed_repo.repo if parsed_repo else None,
                started_at=started_at,
                ended_at=_now(),
                duration_ms=_duration_ms(started),
                error_code=exc.code,
                error_message=exc.message,
            )
        )
        raise

    response = RepoScanResponse(
        owner=parsed_repo.owner,
        repo=parsed_repo.repo,
        repo_url=parsed_repo.repo_url,
        file_tree=file_tree,
        basic_files=basic_files,
    )
    _record_repo_metrics(
        RepoOperationMetrics(
            operation="repo_scan",
            status="success",
            repo_url=parsed_repo.repo_url,
            owner=parsed_repo.owner,
            repo=parsed_repo.repo,
            started_at=started_at,
            ended_at=_now(),
            duration_ms=_duration_ms(started),
            cloned=True,
            file_tree_node_count=count_file_tree_nodes(file_tree),
            basic_file_count=len(basic_files),
            basic_file_bytes=sum(file.size for file in basic_files),
        )
    )
    return response


def _record_repo_metrics(record: RepoOperationMetrics) -> None:
    record_repo_operation_metrics(record, metrics_file=settings.metrics_path)


def _now() -> datetime:
    return datetime.now(UTC)


def _duration_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
