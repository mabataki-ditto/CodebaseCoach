import re
from urllib.parse import urlparse

from app.core.errors import AppError
from app.schemas.repo import RepoParseResponse

_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def parse_github_repo_url(repo_url: str) -> RepoParseResponse:
    raw_url = _normalize_repo_input(repo_url)
    parsed = urlparse(raw_url)

    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid_url_error()

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 2:
        raise _invalid_url_error()

    owner, repo = path_parts
    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo or not _OWNER_PATTERN.fullmatch(owner) or not _REPO_PATTERN.fullmatch(repo):
        raise _invalid_url_error()

    canonical_url = f"https://github.com/{owner}/{repo}"
    return RepoParseResponse(owner=owner, repo=repo, repo_url=canonical_url)


def _invalid_url_error() -> AppError:
    return AppError(
        status_code=400,
        code="INVALID_GITHUB_URL",
        message="GitHub 仓库地址无效",
        detail="支持 https://github.com/owner/repo、https://github.com/owner/repo.git、owner/repo 或 Markdown 链接",
    )


def _normalize_repo_input(repo_url: str) -> str:
    raw_url = repo_url.strip()
    markdown_match = re.fullmatch(r"\[[^\]]+\]\((https://github\.com/[^)\s]+)\)", raw_url)
    if markdown_match:
        return markdown_match.group(1)

    shorthand_match = re.fullmatch(r"([A-Za-z0-9-]+/[A-Za-z0-9._-]+(?:\.git)?)", raw_url)
    if shorthand_match:
        return f"https://github.com/{shorthand_match.group(1)}"

    return raw_url
