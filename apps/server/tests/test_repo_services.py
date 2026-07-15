import tempfile
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.schemas.history import HistoryRecord
from app.services.doc_storage_service import load_markdown_documents_for_history, save_markdown_documents
from app.services.file_selector_service import select_core_files, select_core_files_with_metrics
from app.services.file_tree_service import build_file_tree, read_basic_files, scan_repo_metrics
from app.services.repo_parser import parse_github_repo_url
from app.services.history_service import add_history_record, delete_history_record, list_history_records

pytestmark = pytest.mark.unit


def test_parse_https_github_repo_url() -> None:
    parsed = parse_github_repo_url("https://github.com/modelcontextprotocol/typescript-sdk")

    assert parsed.owner == "modelcontextprotocol"
    assert parsed.repo == "typescript-sdk"
    assert parsed.repo_url == "https://github.com/modelcontextprotocol/typescript-sdk"


def test_parse_trims_git_suffix() -> None:
    parsed = parse_github_repo_url("https://github.com/owner/example.git")

    assert parsed.owner == "owner"
    assert parsed.repo == "example"
    assert parsed.repo_url == "https://github.com/owner/example"


def test_parse_markdown_link() -> None:
    parsed = parse_github_repo_url("[bb-cccc/vibe-upskill](https://github.com/bb-cccc/vibe-upskill)")

    assert parsed.owner == "bb-cccc"
    assert parsed.repo == "vibe-upskill"
    assert parsed.repo_url == "https://github.com/bb-cccc/vibe-upskill"


def test_parse_owner_repo_shorthand() -> None:
    parsed = parse_github_repo_url("bb-cccc/vibe-upskill")

    assert parsed.owner == "bb-cccc"
    assert parsed.repo == "vibe-upskill"
    assert parsed.repo_url == "https://github.com/bb-cccc/vibe-upskill"


def test_invalid_url_raises_app_error() -> None:
    with pytest.raises(AppError) as ctx:
        parse_github_repo_url("https://example.com/owner/repo")

    assert ctx.value.status_code == 400
    assert ctx.value.code == "INVALID_GITHUB_URL"


def test_build_file_tree_filters_runtime_directories() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "src" / "main.ts").write_text("console.log('ok')", encoding="utf-8")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "HEAD").write_text("ignored", encoding="utf-8")

        tree = build_file_tree(root)

    names = {node.name for node in tree}
    assert "src" in names
    assert "node_modules" not in names
    assert ".git" not in names


def test_scan_repo_metrics_counts_files_and_ignored_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("readme", encoding="utf-8")
        (root / "src").mkdir()
        (root / "src" / "main.ts").write_text("console.log('ok')", encoding="utf-8")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "HEAD").write_text("ignored", encoding="utf-8")
        (root / "dist").mkdir()
        (root / "dist" / "bundle.js").write_text("ignored", encoding="utf-8")

        metrics = scan_repo_metrics(root)

    assert metrics.total_files == 2
    assert metrics.ignored_dirs == 3


def test_read_basic_files_limits_content_size() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("a" * 32, encoding="utf-8")
        (root / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
        (root / "src").mkdir()
        (root / "src" / "ignored.ts").write_text("ignored", encoding="utf-8")

        files = read_basic_files(root, max_bytes=10)

    by_path = {file.path: file for file in files}
    assert by_path["README.md"].content_preview == "a" * 10
    assert by_path["README.md"].truncated
    assert "package.json" in by_path
    assert "src/ignored.ts" not in by_path


def test_select_core_files_prioritizes_project_files_and_filters_noise() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("readme", encoding="utf-8")
        (root / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
        (root / "pyproject.toml").write_text("[project]\nname='demo'", encoding="utf-8")
        (root / "src").mkdir()
        (root / "src" / "main.ts").write_text("console.log('entry')", encoding="utf-8")
        (root / "src" / "index.ts").write_text("export {}", encoding="utf-8")
        (root / "app").mkdir()
        (root / "app" / "main.py").write_text("print('api')", encoding="utf-8")
        (root / "services").mkdir()
        (root / "services" / "repo_service.py").write_text("class RepoService: pass", encoding="utf-8")
        (root / "test").mkdir()
        (root / "test" / "main.test.ts").write_text("ignored", encoding="utf-8")
        (root / "dist").mkdir()
        (root / "dist" / "bundle.js").write_text("ignored", encoding="utf-8")
        (root / "src" / "image.png").write_bytes(b"\x00\x01\x02")

        files = select_core_files(root, max_files=12, max_bytes=10)

    paths = [file.path for file in files]
    assert len(files) == 4
    assert len(files) <= 12
    assert "README.md" not in paths
    assert "package.json" not in paths
    assert "pyproject.toml" not in paths
    assert "src/main.ts" in paths
    assert "src/index.ts" in paths
    assert "app/main.py" in paths
    assert "test/main.test.ts" not in paths
    assert "dist/bundle.js" not in paths
    assert "src/image.png" not in paths


def test_select_core_files_limits_content_preview() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.py").write_text("a" * 32, encoding="utf-8")

        files = select_core_files(root, max_files=12, max_bytes=8)

    assert files[0].content_preview == "a" * 8
    assert files[0].truncated


def test_select_core_files_with_metrics_counts_candidate_chars() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("a" * 10, encoding="utf-8")
        (root / "src").mkdir()
        (root / "src" / "main.ts").write_text("b" * 20, encoding="utf-8")
        (root / "src" / "image.png").write_bytes(b"\0binary")

        files, metrics = select_core_files_with_metrics(root, max_files=1, max_bytes=8)

    assert len(files) == 1
    assert metrics.candidate_core_files == 1
    assert metrics.raw_candidate_chars == 20


def test_save_markdown_documents_writes_files_under_generated_docs_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        docs_root = Path(tmp) / "generated_docs"

        documents, docs_dir = save_markdown_documents(
            owner="owner",
            repo="demo",
            docs_root=docs_root,
            documents=[
                ("项目概览", "01-project-overview.md", "# Demo\n"),
                ("面试问题", "02-interview.md", "## Q&A\n"),
            ],
        )

        saved_paths = [docs_root / document.path.removeprefix("generated_docs/") for document in documents]
        assert len(documents) == 2
        assert docs_dir.startswith("generated_docs/owner_demo_")
        assert all(path.exists() for path in saved_paths)
        assert saved_paths[0].read_text(encoding="utf-8") == "# Demo\n"


def test_load_markdown_documents_for_history_reads_saved_docs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        docs_root = Path(tmp) / "generated_docs"
        documents, docs_dir = save_markdown_documents(
            owner="owner",
            repo="demo",
            docs_root=docs_root,
            documents=[("Overview", "01-overview.md", "# Demo\n")],
        )
        record = HistoryRecord(
            id="history-1",
            repo_url="https://github.com/owner/demo",
            owner="owner",
            repo="demo",
            status="success",
            created_at="2026-06-30T00:00:00Z",
            completed_at="2026-06-30T00:00:01Z",
            docs_dir=docs_dir,
            core_files_count=1,
        )

        loaded = load_markdown_documents_for_history(docs_root=docs_root, history_record=record)

    assert len(loaded) == len(documents)
    assert loaded[0].filename == "01-overview.md"
    assert loaded[0].content == "# Demo\n"


def test_load_markdown_documents_for_history_rejects_empty_docs_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        record = HistoryRecord(
            id="history-1",
            repo_url="https://github.com/owner/demo",
            owner="owner",
            repo="demo",
            status="failed",
            created_at="2026-06-30T00:00:00Z",
            completed_at="2026-06-30T00:00:01Z",
            docs_dir="",
            core_files_count=0,
        )

        with pytest.raises(AppError) as ctx:
            load_markdown_documents_for_history(docs_root=Path(tmp) / "generated_docs", history_record=record)

    assert ctx.value.status_code == 404
    assert ctx.value.code == "DOCS_NOT_FOUND"


def test_add_and_list_history_records(db_session_factory) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        history_file = Path(tmp) / "data" / "history.json"

        record = add_history_record(
            history_file=history_file,
            repo_url="https://github.com/owner/demo",
            owner="owner",
            repo="demo",
            status="success",
            created_at="2026-06-30T00:00:00Z",
            completed_at="2026-06-30T00:00:01Z",
            docs_dir="generated_docs/owner_demo_1",
            core_files_count=3,
            session_factory=db_session_factory,
        )
        records = list_history_records(history_file=history_file, session_factory=db_session_factory)

    assert len(records) == 1
    assert records[0].id == record.id
    assert records[0].core_files_count == 3
    assert not history_file.exists()


def test_delete_history_record_does_not_delete_generated_docs(db_session_factory) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        history_file = root / "data" / "history.json"
        docs_dir = root / "generated_docs" / "owner_demo_1"
        docs_dir.mkdir(parents=True)
        doc_path = docs_dir / "01-overview.md"
        doc_path.write_text("# Demo\n", encoding="utf-8")

        record = add_history_record(
            history_file=history_file,
            repo_url="https://github.com/owner/demo",
            owner="owner",
            repo="demo",
            status="success",
            created_at="2026-06-30T00:00:00Z",
            completed_at="2026-06-30T00:00:01Z",
            docs_dir="generated_docs/owner_demo_1",
            core_files_count=1,
            session_factory=db_session_factory,
        )
        deleted = delete_history_record(
            history_file=history_file,
            record_id=record.id,
            session_factory=db_session_factory,
        )
        doc_still_exists = doc_path.exists()

    assert deleted
    assert doc_still_exists
