import pytest

from app.core.errors import AppError
from app.services.repo_parser import parse_github_repo_url


@pytest.mark.parametrize(
    "repo_url, expected_owner, expected_repo, expected_canonical_url",
    [
        pytest.param(
            "https://github.com/vuejs/vue",
            "vuejs",
            "vue",
            "https://github.com/vuejs/vue",
            id="完整-GitHub-URL",
        ),
        pytest.param(
            "https://github.com/vuejs/vue.git",
            "vuejs",
            "vue",
            "https://github.com/vuejs/vue",
            id="git-后缀",
        ),
        pytest.param(
            "vuejs/vue",
            "vuejs",
            "vue",
            "https://github.com/vuejs/vue",
            id="owner-repo-简写",
        ),
        pytest.param(
            "[Vue](https://github.com/vuejs/vue)",
            "vuejs",
            "vue",
            "https://github.com/vuejs/vue",
            id="Markdown-链接",
        ),
    ],
)
def test_parse_supported_repo_inputs(
    repo_url: str,
    expected_owner: str,
    expected_repo: str,
    expected_canonical_url: str,
) -> None:
    result = parse_github_repo_url(repo_url)

    assert result.owner == expected_owner
    assert result.repo == expected_repo
    assert result.repo_url == expected_canonical_url


@pytest.mark.parametrize(
    "repo_url",
    [
        pytest.param(
            "https://example.com/vue/vue",
            id="非法域名",
        ),
        pytest.param(
            "http://github.com/vuejs/vue",
            id="HTTP协议",
        ),
        pytest.param(
            "https://github.com/vuejs",
            id="路径层级错误",
        ),
        pytest.param(
            "https://github.com/vue_js/vue",
            id="非法owner字符",
        ),
    ],
)
def test_parse_rejects_invalid_repo_urls(repo_url: str) -> None:
    with pytest.raises(AppError) as exc_info:
        parse_github_repo_url(repo_url)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_GITHUB_URL"