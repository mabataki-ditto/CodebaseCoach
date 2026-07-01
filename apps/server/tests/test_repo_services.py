import tempfile
import unittest
from pathlib import Path

from app.core.errors import AppError
from app.schemas.history import HistoryRecord
from app.services.doc_storage_service import load_markdown_documents_for_history, save_markdown_documents
from app.services.file_selector_service import select_core_files, select_core_files_with_metrics
from app.services.file_tree_service import build_file_tree, read_basic_files, scan_repo_metrics
from app.services.repo_parser import parse_github_repo_url
from app.services.history_service import add_history_record, delete_history_record, list_history_records


class RepoParserTests(unittest.TestCase):
    def test_parse_https_github_repo_url(self) -> None:
        parsed = parse_github_repo_url("https://github.com/modelcontextprotocol/typescript-sdk")

        self.assertEqual(parsed.owner, "modelcontextprotocol")
        self.assertEqual(parsed.repo, "typescript-sdk")
        self.assertEqual(
            parsed.repo_url,
            "https://github.com/modelcontextprotocol/typescript-sdk",
        )

    def test_parse_trims_git_suffix(self) -> None:
        parsed = parse_github_repo_url("https://github.com/owner/example.git")

        self.assertEqual(parsed.owner, "owner")
        self.assertEqual(parsed.repo, "example")
        self.assertEqual(parsed.repo_url, "https://github.com/owner/example")

    def test_parse_markdown_link(self) -> None:
        parsed = parse_github_repo_url("[bb-cccc/vibe-upskill](https://github.com/bb-cccc/vibe-upskill)")

        self.assertEqual(parsed.owner, "bb-cccc")
        self.assertEqual(parsed.repo, "vibe-upskill")
        self.assertEqual(parsed.repo_url, "https://github.com/bb-cccc/vibe-upskill")

    def test_parse_owner_repo_shorthand(self) -> None:
        parsed = parse_github_repo_url("bb-cccc/vibe-upskill")

        self.assertEqual(parsed.owner, "bb-cccc")
        self.assertEqual(parsed.repo, "vibe-upskill")
        self.assertEqual(parsed.repo_url, "https://github.com/bb-cccc/vibe-upskill")

    def test_invalid_url_raises_app_error(self) -> None:
        with self.assertRaises(AppError) as ctx:
            parse_github_repo_url("https://example.com/owner/repo")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.code, "INVALID_GITHUB_URL")


class FileTreeTests(unittest.TestCase):
    def test_build_file_tree_filters_runtime_directories(self) -> None:
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
        self.assertIn("src", names)
        self.assertNotIn("node_modules", names)
        self.assertNotIn(".git", names)

    def test_scan_repo_metrics_counts_files_and_ignored_dirs(self) -> None:
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

        self.assertEqual(metrics.total_files, 2)
        self.assertEqual(metrics.ignored_dirs, 3)

    def test_read_basic_files_limits_content_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("a" * 32, encoding="utf-8")
            (root / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "ignored.ts").write_text("ignored", encoding="utf-8")

            files = read_basic_files(root, max_bytes=10)

        by_path = {file.path: file for file in files}
        self.assertEqual(by_path["README.md"].content_preview, "a" * 10)
        self.assertTrue(by_path["README.md"].truncated)
        self.assertIn("package.json", by_path)
        self.assertNotIn("src/ignored.ts", by_path)


class CoreFileSelectorTests(unittest.TestCase):
    def test_select_core_files_prioritizes_project_files_and_filters_noise(self) -> None:
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
        self.assertGreaterEqual(len(files), 5)
        self.assertLessEqual(len(files), 12)
        self.assertEqual(paths[:3], ["README.md", "package.json", "pyproject.toml"])
        self.assertIn("src/main.ts", paths)
        self.assertIn("app/main.py", paths)
        self.assertNotIn("test/main.test.ts", paths)
        self.assertNotIn("dist/bundle.js", paths)
        self.assertNotIn("src/image.png", paths)

    def test_select_core_files_limits_content_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("a" * 32, encoding="utf-8")

            files = select_core_files(root, max_files=12, max_bytes=8)

        self.assertEqual(files[0].content_preview, "a" * 8)
        self.assertTrue(files[0].truncated)

    def test_select_core_files_with_metrics_counts_candidate_chars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("a" * 10, encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "main.ts").write_text("b" * 20, encoding="utf-8")
            (root / "src" / "image.png").write_bytes(b"\0binary")

            files, metrics = select_core_files_with_metrics(root, max_files=1, max_bytes=8)

        self.assertEqual(len(files), 1)
        self.assertEqual(metrics.candidate_core_files, 2)
        self.assertEqual(metrics.raw_candidate_chars, 30)


class DocStorageTests(unittest.TestCase):
    def test_save_markdown_documents_writes_files_under_generated_docs_root(self) -> None:
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
            self.assertEqual(len(documents), 2)
            self.assertTrue(docs_dir.startswith("generated_docs/owner_demo_"))
            self.assertTrue(all(path.exists() for path in saved_paths))
            self.assertEqual(saved_paths[0].read_text(encoding="utf-8"), "# Demo\n")

    def test_load_markdown_documents_for_history_reads_saved_docs(self) -> None:
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

        self.assertEqual(len(loaded), len(documents))
        self.assertEqual(loaded[0].filename, "01-overview.md")
        self.assertEqual(loaded[0].content, "# Demo\n")

    def test_load_markdown_documents_for_history_rejects_empty_docs_dir(self) -> None:
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

            with self.assertRaises(AppError) as ctx:
                load_markdown_documents_for_history(docs_root=Path(tmp) / "generated_docs", history_record=record)

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.code, "DOCS_NOT_FOUND")


class HistoryServiceTests(unittest.TestCase):
    def test_add_and_list_history_records(self) -> None:
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
            )
            records = list_history_records(history_file=history_file)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].id, record.id)
        self.assertEqual(records[0].core_files_count, 3)

    def test_delete_history_record_does_not_delete_generated_docs(self) -> None:
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
            )
            deleted = delete_history_record(history_file=history_file, record_id=record.id)
            doc_still_exists = doc_path.exists()

        self.assertTrue(deleted)
        self.assertTrue(doc_still_exists)


if __name__ == "__main__":
    unittest.main()
