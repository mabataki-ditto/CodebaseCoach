from collections.abc import Iterable
import re
from time import perf_counter
from typing import Any

from app.agent.prompts import DocumentPrompt, SYSTEM_PROMPT
from app.core.errors import AppError
from app.services.llm_call_service import LLMCallService

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised only before dependencies are installed
    OpenAI = None  # type: ignore[assignment]


DEFAULT_MAX_OUTPUT_TOKENS = 1800
DEFAULT_PROVIDER = "openai"


def has_llm_credentials(api_key: str | None) -> bool:
    if not api_key:
        return False
    normalized = api_key.strip()
    return bool(normalized and normalized not in {"your_api_key_here", "your_llm_api_key_here"})


def has_openai_credentials(api_key: str | None) -> bool:
    return has_llm_credentials(api_key)


def generate_markdown_documents(
    *,
    document_prompts: Iterable[DocumentPrompt],
    context: str,
    api_key: str | None,
    model: str,
    base_url: str | None = None,
    recorder: LLMCallService | None = None,
) -> list[tuple[str, str, str]]:
    if not has_llm_credentials(api_key):
        raise AppError(
            status_code=400,
            code="LLM_API_KEY_MISSING",
            message="未配置 LLM API Key，无法调用真实 AI",
        )
    if OpenAI is None:
        raise AppError(
            status_code=500,
            code="LLM_DEPENDENCY_MISSING",
            message="OpenAI-compatible Python SDK 未安装",
            detail="请先运行 pip install -r requirements.txt",
        )

    client_kwargs: dict[str, str] = {"api_key": api_key.strip()}
    if base_url:
        client_kwargs["base_url"] = base_url.strip()
    client = OpenAI(**client_kwargs)
    documents: list[tuple[str, str, str]] = []
    for prompt in document_prompts:
        started = perf_counter()
        try:
            content = _generate_single_document(
                client=client,
                prompt=prompt.instruction,
                context=context,
                model=model,
                api_key=api_key,
            )
        except AppError as exc:
            if recorder is not None:
                recorder.record(
                    prompt_type=prompt.title,
                    duration_ms=int((perf_counter() - started) * 1000),
                    status="failed",
                    error_message=exc.message,
                )
            raise
        if recorder is not None:
            recorder.record(
                prompt_type=prompt.title,
                duration_ms=int((perf_counter() - started) * 1000),
                status="success",
            )
        documents.append((prompt.title, prompt.filename, content))
    return documents


def _generate_single_document(
    *,
    client: Any,
    prompt: str,
    context: str,
    model: str,
    api_key: str,
) -> str:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"{prompt}\n\n# 已读取的仓库上下文\n\n{context}",
                },
            ],
            max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
            stream=False,
        )
    except Exception as exc:
        raise AppError(
            status_code=502,
            code="LLM_CALL_FAILED",
            message="AI 文档生成失败",
            detail=_safe_error_detail(exc, api_key=api_key),
        ) from exc

    content = _extract_output_text(response).strip()
    if not content:
        raise AppError(
            status_code=502,
            code="LLM_EMPTY_RESPONSE",
            message="AI 文档生成失败",
            detail="LLM 返回内容为空",
        )
    return content


def _extract_output_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text

    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if isinstance(text, str):
                parts.append(text)
            elif isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)


def _safe_error_detail(exc: Exception, *, api_key: str) -> str:
    detail = str(exc)[:500]
    if api_key:
        detail = detail.replace(api_key, "[redacted-llm-key]")
    return re.sub(r"sk-[A-Za-z0-9_-]{20,}", "[redacted-llm-key]", detail)
