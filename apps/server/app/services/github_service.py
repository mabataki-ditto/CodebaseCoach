from datetime import UTC, datetime
from pathlib import Path
import re

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo

from app.core.errors import AppError
from app.schemas.repo import RepoParseResponse


def clone_repository(parsed_repo: RepoParseResponse, temp_repo_root: Path) -> Path:
    temp_repo_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    target_dir = temp_repo_root / f"{_safe_path_part(parsed_repo.owner)}_{_safe_path_part(parsed_repo.repo)}_{timestamp}"
    resolved_target = target_dir.resolve()

    if not _is_relative_to(resolved_target, temp_repo_root.resolve()):
        raise AppError(
            status_code=400,
            code="INVALID_REPO_PATH",
            message="仓库本地路径无效",
        )

    try:
        Repo.clone_from(parsed_repo.repo_url, resolved_target, depth=1)
    except GitCommandError as exc:
        raise AppError(
            status_code=502,
            code="REPO_CLONE_FAILED",
            message="仓库克隆失败",
            detail=str(exc),
        ) from exc

    return resolved_target


def get_repository_commit_sha(local_path: Path) -> str:
    """Return the checked-out commit without putting a Git object in graph state."""
    try:
        return Repo(local_path).head.commit.hexsha
    except (InvalidGitRepositoryError, NoSuchPathError, ValueError):
        return ""


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
