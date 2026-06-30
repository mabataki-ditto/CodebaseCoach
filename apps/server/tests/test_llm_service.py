import unittest

from app.services.llm_service import _safe_error_detail, has_openai_credentials


class LlmServiceTests(unittest.TestCase):
    def test_has_openai_credentials_rejects_empty_and_placeholder_values(self) -> None:
        self.assertFalse(has_openai_credentials(None))
        self.assertFalse(has_openai_credentials(""))
        self.assertFalse(has_openai_credentials("your_api_key_here"))
        self.assertTrue(has_openai_credentials("sk-test-value"))

    def test_safe_error_detail_redacts_openai_keys(self) -> None:
        detail = _safe_error_detail(
            RuntimeError("request failed for sk-abcdefghijklmnopqrstuvwxyz123456"),
            api_key="sk-abcdefghijklmnopqrstuvwxyz123456",
        )

        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", detail)
        self.assertIn("[redacted-openai-key]", detail)


if __name__ == "__main__":
    unittest.main()
