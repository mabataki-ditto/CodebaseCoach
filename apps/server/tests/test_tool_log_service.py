import unittest

from app.core.errors import AppError
from app.services.tool_log_service import record_tool_call


class ToolLogServiceTests(unittest.TestCase):
    def test_record_tool_call_adds_registry_audit_metadata(self) -> None:
        logs = []

        log = record_tool_call(
            logs,
            tool_name="clone_repository",
            status="success",
            input_summary="https://github.com/owner/repo",
            output_summary="repo",
            input_payload={"repo_url": "https://github.com/owner/repo"},
            output_payload={"local_path": "temp_repos/repo"},
            duration_ms=12,
        )

        self.assertEqual(log.tool_provider, "builtin")
        self.assertEqual(log.permission, "network")
        self.assertFalse(log.requires_confirmation)
        self.assertIn("repo_url", log.input_schema["properties"])
        self.assertEqual(log.input["repo_url"], "https://github.com/owner/repo")
        self.assertEqual(logs[0], log)

    def test_record_tool_call_redacts_sensitive_input_fields(self) -> None:
        logs = []

        log = record_tool_call(
            logs,
            tool_name="llm_service.generate_markdown_documents",
            status="success",
            input_summary="provider=openai",
            output_summary="Generated 1 document",
            input_payload={"provider": "openai", "api_key": "sk-secret", "token": "secret-token"},
            output_payload={"documents": ["01.md"]},
            duration_ms=20,
        )

        self.assertEqual(log.permission, "llm")
        self.assertEqual(log.input["api_key"], "[redacted]")
        self.assertEqual(log.input["token"], "[redacted]")
        self.assertEqual(log.input["provider"], "openai")

    def test_record_tool_call_rejects_unregistered_tools(self) -> None:
        with self.assertRaises(AppError) as raised:
            record_tool_call(
                [],
                tool_name="unknown_tool",
                status="success",
                input_summary="",
                output_summary="",
                duration_ms=0,
            )

        self.assertEqual(raised.exception.code, "TOOL_NOT_REGISTERED")


if __name__ == "__main__":
    unittest.main()
