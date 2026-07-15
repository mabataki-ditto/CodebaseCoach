from fastapi import APIRouter

from app.core.config import settings
from app.schemas.repo import RepoParseResponse, RepoRequest, RepoScanResponse
from app.services.file_tree_service import build_file_tree, read_basic_files
from app.services.github_service import clone_repository
from app.services.repo_parser import parse_github_repo_url

router = APIRouter(prefix="/api/repo", tags=["repo"])


@router.post("/parse", response_model=RepoParseResponse)
def parse_repo(request: RepoRequest) -> RepoParseResponse:
    return parse_github_repo_url(request.repo_url)


@router.post("/scan", response_model=RepoScanResponse)
def scan_repo(request: RepoRequest) -> RepoScanResponse:
    parsed_repo = parse_github_repo_url(request.repo_url)
    local_path = clone_repository(parsed_repo, settings.temp_repo_path)
    file_tree = build_file_tree(
        local_path,
        max_depth=settings.max_file_tree_depth,
        max_entries=settings.max_file_tree_entries,
    )
    basic_files = read_basic_files(local_path, max_bytes=settings.max_basic_file_bytes)
    return RepoScanResponse(
        owner=parsed_repo.owner,
        repo=parsed_repo.repo,
        repo_url=parsed_repo.repo_url,
        file_tree=file_tree,
        basic_files=basic_files,
    )
