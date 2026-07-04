import unittest

from app.agent.prompts import DocumentPrompt
from app.core.errors import AppError
from app.services.llm_call_service import LLMCallService
from app.services.llm_service import _safe_error_detail, generate_markdown_documents, has_llm_credentials
import app.services.llm_service as llm_service


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = text


class _FakeChoice:
    def __init__(self, text: str) -> None:
        self.message = _FakeMessage(text)


class _FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class _FakeChatResponse:
    def __init__(self, text: str, usage: _FakeUsage | None = None) -> None:
        self.choices = [_FakeChoice(text)]
        self.usage = usage


class _FakeCompletions:
    def __init__(self, texts: list[str], usages: list[_FakeUsage] | None = None) -> None:
        self._texts = list(texts)
        self._usages = list(usages or [])
        self._index = 0
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeChatResponse:
        self.calls.append(kwargs)
        text = self._texts[self._index]
        usage = self._usages[self._index] if self._index < len(self._usages) else None
        self._index += 1
        return _FakeChatResponse(text, usage)


class _FakeChat:
    def __init__(self, texts: list[str], usages: list[_FakeUsage] | None = None) -> None:
        self.completions = _FakeCompletions(texts, usages)


class _FakeClient:
    def __init__(self, texts: list[str], usages: list[_FakeUsage] | None = None) -> None:
        self.chat = _FakeChat(texts, usages)


class _FakeOpenAI:
    def __init__(self, *, texts: list[str], usages: list[_FakeUsage] | None = None) -> None:
        self._texts = texts
        self._usages = usages
        self.init_kwargs: dict[str, object] | None = None
        self.client: _FakeClient | None = None

    def __call__(self, **kwargs: object) -> _FakeClient:
        self.init_kwargs = kwargs
        self.client = _FakeClient(self._texts, self._usages)
        return self.client


class _FakeFailingCompletions:
    def create(self, **_: object) -> _FakeChatResponse:
        raise RuntimeError("boom")


class _FakeFailingChat:
    def __init__(self) -> None:
        self.completions = _FakeFailingCompletions()


class _FakeFailingClient:
    def __init__(self) -> None:
        self.chat = _FakeFailingChat()


class _FakeFailingOpenAI:
    def __call__(self, **_: object) -> _FakeFailingClient:
        return _FakeFailingClient()


class LlmServiceTests(unittest.TestCase):
    def test_has_llm_credentials_rejects_empty_and_placeholder_values(self) -> None:
        self.assertFalse(has_llm_credentials(None))
        self.assertFalse(has_llm_credentials(""))
        self.assertFalse(has_llm_credentials("your_api_key_here"))
        self.assertFalse(has_llm_credentials("your_llm_api_key_here"))
        self.assertTrue(has_llm_credentials("test-value"))

    def test_safe_error_detail_redacts_llm_keys(self) -> None:
        detail = _safe_error_detail(
            RuntimeError("request failed for sk-abcdefghijklmnopqrstuvwxyz123456"),
            api_key="sk-abcdefghijklmnopqrstuvwxyz123456",
        )

        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", detail)
        self.assertIn("[redacted-llm-key]", detail)

    def test_generate_markdown_documents_uses_openai_compatible_chat_completions(self) -> None:
        original_openai = llm_service.OpenAI
        fake_openai = _FakeOpenAI(texts=["doc1 body", "doc2 body"])
        llm_service.OpenAI = fake_openai
        try:
            recorder = LLMCallService(provider="deepseek", model="test-model")
            documents = generate_markdown_documents(
                document_prompts=[
                    DocumentPrompt(title="项目概览", filename="01.md", instruction="x"),
                    DocumentPrompt(title="技术栈", filename="02.md", instruction="y"),
                ],
                context="ctx",
                api_key="test-api-key",
                model="test-model",
                base_url="https://api.deepseek.com",
                recorder=recorder,
            )
        finally:
            llm_service.OpenAI = original_openai

        self.assertEqual(len(documents), 2)
        self.assertEqual(fake_openai.init_kwargs, {"api_key": "test-api-key", "base_url": "https://api.deepseek.com"})
        self.assertIsNotNone(fake_openai.client)
        calls = fake_openai.client.chat.completions.calls if fake_openai.client is not None else []
        self.assertEqual(calls[0]["model"], "test-model")
        self.assertEqual(calls[0]["stream"], False)
        self.assertIn("messages", calls[0])
        records = recorder.records
        self.assertEqual(len(records), 2)
        self.assertEqual([record.status for record in records], ["success", "success"])
        self.assertEqual([record.prompt_type for record in records], ["项目概览", "技术栈"])
        self.assertTrue(all(record.duration_ms >= 0 for record in records))
        self.assertTrue(all(record.provider == "deepseek" for record in records))
        self.assertTrue(all(record.model == "test-model" for record in records))

    def test_generate_markdown_documents_records_token_usage(self) -> None:
        original_openai = llm_service.OpenAI
        fake_openai = _FakeOpenAI(
            texts=["doc body"],
            usages=[_FakeUsage(prompt_tokens=11, completion_tokens=7, total_tokens=18)],
        )
        llm_service.OpenAI = fake_openai
        try:
            recorder = LLMCallService(provider="openai", model="test-model")
            generate_markdown_documents(
                document_prompts=[DocumentPrompt(title="项目概览", filename="01.md", instruction="x")],
                context="ctx",
                api_key="test-api-key",
                model="test-model",
                recorder=recorder,
            )
        finally:
            llm_service.OpenAI = original_openai

        records = recorder.records
        self.assertEqual(records[0].input_tokens, 11)
        self.assertEqual(records[0].output_tokens, 7)
        self.assertEqual(records[0].total_tokens, 18)

    def test_generate_markdown_documents_records_failed_call(self) -> None:
        original_openai = llm_service.OpenAI
        llm_service.OpenAI = _FakeFailingOpenAI()
        try:
            recorder = LLMCallService(provider="openai", model="test-model")
            with self.assertRaises(AppError) as raised:
                generate_markdown_documents(
                    document_prompts=[
                        DocumentPrompt(title="项目概览", filename="01.md", instruction="x"),
                    ],
                    context="ctx",
                    api_key="test-api-key",
                    model="test-model",
                    recorder=recorder,
                )
        finally:
            llm_service.OpenAI = original_openai

        records = recorder.records
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, "failed")
        self.assertIsNotNone(records[0].error_message)
        self.assertEqual(raised.exception.code, "LLM_CALL_FAILED")


if __name__ == "__main__":
    unittest.main()
