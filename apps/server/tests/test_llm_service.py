import threading

import pytest

from app.agent.prompts import DocumentPrompt, REAL_DOCUMENT_PROMPTS
from app.core.errors import AppError
from app.services.llm_call_service import LLMCallService
from app.services.llm_service import (
    _safe_error_detail,
    generate_markdown_document,
    generate_markdown_documents,
    has_llm_credentials,
)
import app.services.llm_service as llm_service


pytestmark = pytest.mark.unit


def test_real_document_prompts_define_adapted_length_targets() -> None:
    expected_targets = {
        "01-项目概览.md": "中文正文约 1200～1800 字",
        "02-技术栈分析.md": "中文正文约 1200～1800 字",
        "03-核心模块解析.md": "中文正文约 1800～2600 字",
        "04-核心流程说明.md": "中文正文约 1600～2400 字",
        "05-面试问题与回答.md": "中文正文约 2400～3400 字",
        "06-简历描述.md": "中文正文约 800～1200 字",
        "07-可贡献PR方向.md": "中文正文约 1400～2200 字",
    }

    assert {prompt.filename for prompt in REAL_DOCUMENT_PROMPTS} == set(expected_targets)
    for prompt in REAL_DOCUMENT_PROMPTS:
        assert expected_targets[prompt.filename] in prompt.instruction
        assert "信息不足时宁可缩短，也不要重复或编造" in prompt.instruction


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
        self._lock = threading.Lock()
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeChatResponse:
        with self._lock:
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


def test_has_llm_credentials_rejects_empty_and_placeholder_values() -> None:
    assert not has_llm_credentials(None)
    assert not has_llm_credentials("")
    assert not has_llm_credentials("your_api_key_here")
    assert not has_llm_credentials("your_llm_api_key_here")
    assert has_llm_credentials("test-value")


def test_safe_error_detail_redacts_llm_keys() -> None:
    detail = _safe_error_detail(
        RuntimeError("request failed for sk-abcdefghijklmnopqrstuvwxyz123456"),
        api_key="sk-abcdefghijklmnopqrstuvwxyz123456",
    )

    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in detail
    assert "[redacted-llm-key]" in detail


def test_generate_markdown_documents_uses_openai_compatible_chat_completions() -> None:
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

    assert len(documents) == 2
    assert fake_openai.init_kwargs == {"api_key": "test-api-key", "base_url": "https://api.deepseek.com"}
    assert fake_openai.client is not None
    calls = fake_openai.client.chat.completions.calls
    assert calls[0]["model"] == "test-model"
    assert calls[0]["max_tokens"] == 8192
    assert calls[0]["stream"] is False
    assert "messages" in calls[0]
    records = recorder.records
    assert len(records) == 2
    assert [record.status for record in records] == ["success", "success"]
    assert [record.prompt_type for record in records] == ["项目概览", "技术栈"]
    assert all(record.duration_ms >= 0 for record in records)
    assert all(record.provider == "deepseek" for record in records)
    assert all(record.model == "test-model" for record in records)


def test_generate_markdown_documents_records_token_usage() -> None:
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
    assert records[0].input_tokens == 11
    assert records[0].output_tokens == 7
    assert records[0].total_tokens == 18


def test_generate_markdown_documents_records_failed_call() -> None:
    original_openai = llm_service.OpenAI
    llm_service.OpenAI = _FakeFailingOpenAI()
    try:
        recorder = LLMCallService(provider="openai", model="test-model")
        with pytest.raises(AppError) as raised:
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
    assert len(records) == 1
    assert records[0].status == "failed"
    assert records[0].error_message is not None
    assert raised.value.code == "LLM_CALL_FAILED"


def test_generate_markdown_document_uses_existing_openai_compatible_call() -> None:
    original_openai = llm_service.OpenAI
    fake_openai = _FakeOpenAI(
        texts=["doc body"],
        usages=[_FakeUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8)],
    )
    llm_service.OpenAI = fake_openai
    prompt = DocumentPrompt(title="Project overview", filename="01-overview.md", instruction="x")
    try:
        recorder = LLMCallService(provider="deepseek", model="test-model")
        document = generate_markdown_document(
            document_prompt=prompt,
            context="ctx",
            api_key="test-api-key",
            model="test-model",
            base_url="https://api.deepseek.com",
            recorder=recorder,
        )
    finally:
        llm_service.OpenAI = original_openai

    assert document == ("Project overview", "01-overview.md", "doc body")
    assert fake_openai.init_kwargs == {"api_key": "test-api-key", "base_url": "https://api.deepseek.com"}
    assert fake_openai.client is not None
    assert len(fake_openai.client.chat.completions.calls) == 1
    assert recorder.records[0].total_tokens == 8
