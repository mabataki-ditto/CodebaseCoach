import re

from app.schemas.agent import (
    CoreFileSummary,
    GeneratedDocument,
    GeneratedDocumentEvaluation,
    GeneratedResultEvaluation,
)


INTERVIEW_QUESTION_TARGET = 8

_BACKTICK_TOKEN_PATTERN = re.compile(r"`([^`]+)`")
_MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_FILE_LIKE_PATTERN = re.compile(r"(?:^|/)[^/\s]+\.[A-Za-z][A-Za-z0-9]*$")
_TITLE_PATTERN = re.compile(r"^\s*#\s+\S+", re.MULTILINE)
_SECTION_PATTERN = re.compile(r"^\s*#{2,3}\s+\S+", re.MULTILINE)
_INTERVIEW_QUESTION_PATTERN = re.compile(
    r"^\s*#{2,3}\s*(?:(?:Q|Question)\s*)?\d+\s*[\s.:\)\-]|^\s*#{2,3}\s*问题\s*\d+",
    re.IGNORECASE | re.MULTILINE,
)
_PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TODO|TBD|FIXME|lorem ipsum)\b|待补充|不详|不确定但|可以推测|猜测",
    re.IGNORECASE,
)
_INFLATED_CLAIM_PATTERN = re.compile(
    r"千万级|百万用户|高并发|分布式|微服务|Kubernetes|k8s|上线生产|大规模",
    re.IGNORECASE,
)


def evaluate_generated_documents(
    *,
    documents: list[GeneratedDocument],
    core_files: list[CoreFileSummary],
) -> GeneratedResultEvaluation:
    context_paths = {file.path for file in core_files if file.used_for_context}
    document_evaluations = [_evaluate_document(document, context_paths) for document in documents]

    valid_reference_count = sum(len(item.valid_referenced_file_paths) for item in document_evaluations)
    invalid_reference_count = sum(len(item.invalid_referenced_file_paths) for item in document_evaluations)
    total_reference_count = valid_reference_count + invalid_reference_count
    referenced_context_paths = {
        path
        for item in document_evaluations
        for path in item.valid_referenced_file_paths
    }
    placeholder_hit_count = sum(len(item.placeholder_hits) for item in document_evaluations)
    interview_question_count = _count_interview_questions(documents)
    issues = [issue for item in document_evaluations for issue in item.issues]

    if documents and interview_question_count < INTERVIEW_QUESTION_TARGET:
        issues.append(
            f"Interview question count is {interview_question_count}, expected at least {INTERVIEW_QUESTION_TARGET}."
        )

    textcitation_score = valid_reference_count / total_reference_count if total_reference_count else 0
    coverage_score = len(referenced_context_paths) / len(context_paths) if context_paths else 0
    hallucination_risk = (
        (invalid_reference_count + placeholder_hit_count) / (total_reference_count + placeholder_hit_count)
        if total_reference_count + placeholder_hit_count
        else 0
    )
    usefulness_score = _calculate_usefulness_score(
        document_evaluations=document_evaluations,
        invalid_reference_count=invalid_reference_count,
        placeholder_hit_count=placeholder_hit_count,
        valid_reference_count=valid_reference_count,
        interview_question_count=interview_question_count,
    )

    return GeneratedResultEvaluation(
        document_count=len(documents),
        evaluated_document_count=len(document_evaluations),
        textcitation_score=round(textcitation_score, 4),
        coverage_score=round(coverage_score, 4),
        hallucination_risk=round(hallucination_risk, 4),
        usefulness_score=round(usefulness_score, 4),
        valid_reference_count=valid_reference_count,
        invalid_reference_count=invalid_reference_count,
        referenced_context_file_count=len(referenced_context_paths),
        context_file_count=len(context_paths),
        interview_question_count=interview_question_count,
        interview_question_target=INTERVIEW_QUESTION_TARGET,
        document_evaluations=document_evaluations,
        issues=issues,
    )


def _evaluate_document(document: GeneratedDocument, context_paths: set[str]) -> GeneratedDocumentEvaluation:
    referenced_paths = _extract_referenced_paths(document.content)
    valid_paths = [path for path in referenced_paths if path in context_paths]
    invalid_paths = [path for path in referenced_paths if path not in context_paths]
    placeholder_hits = _unique(match.group(0) for match in _PLACEHOLDER_PATTERN.finditer(document.content))
    has_title = bool(document.title.strip()) or bool(_TITLE_PATTERN.search(document.content))
    issues: list[str] = []

    if not has_title:
        issues.append(f"{document.filename}: missing document title.")
    if not _SECTION_PATTERN.search(document.content):
        issues.append(f"{document.filename}: missing second-level sections.")
    if invalid_paths:
        issues.append(f"{document.filename}: references files outside current context: {', '.join(invalid_paths)}.")
    if placeholder_hits:
        issues.append(f"{document.filename}: contains placeholder text: {', '.join(placeholder_hits)}.")
    if _is_pr_document(document) and not valid_paths:
        issues.append(f"{document.filename}: PR guidance has no valid file reference.")
    if _is_resume_document(document) and _INFLATED_CLAIM_PATTERN.search(document.content) and not valid_paths:
        issues.append(f"{document.filename}: resume claims need real file references.")

    return GeneratedDocumentEvaluation(
        filename=document.filename,
        title=document.title,
        has_title=has_title,
        char_count=len(document.content),
        referenced_file_paths=referenced_paths,
        valid_referenced_file_paths=valid_paths,
        invalid_referenced_file_paths=invalid_paths,
        placeholder_hits=placeholder_hits,
        issues=issues,
    )


def _extract_referenced_paths(content: str) -> list[str]:
    tokens = [match.group(1) for match in _BACKTICK_TOKEN_PATTERN.finditer(content)]
    tokens.extend(match.group(1) for match in _MARKDOWN_LINK_PATTERN.finditer(content))
    return _unique(_normalize_path(token) for token in tokens if _is_file_like_token(_normalize_path(token)))


def _is_file_like_token(token: str) -> bool:
    if not token or " " in token:
        return False
    return "/" in token or bool(_FILE_LIKE_PATTERN.search(token))


def _normalize_path(token: str) -> str:
    return token.strip().replace("\\", "/").split("#", 1)[0].split("?", 1)[0]


def _count_interview_questions(documents: list[GeneratedDocument]) -> int:
    return sum(len(_INTERVIEW_QUESTION_PATTERN.findall(document.content)) for document in documents)


def _calculate_usefulness_score(
    *,
    document_evaluations: list[GeneratedDocumentEvaluation],
    invalid_reference_count: int,
    placeholder_hit_count: int,
    valid_reference_count: int,
    interview_question_count: int,
) -> float:
    score = 1.0
    if any(not item.has_title for item in document_evaluations):
        score -= 0.15
    if valid_reference_count == 0:
        score -= 0.25
    if invalid_reference_count:
        score -= 0.25
    if placeholder_hit_count:
        score -= 0.2
    if document_evaluations and interview_question_count < INTERVIEW_QUESTION_TARGET:
        score -= 0.15
    return max(0, min(1, score))


def _is_pr_document(document: GeneratedDocument) -> bool:
    text = f"{document.filename}\n{document.title}\n{document.content}".lower()
    return "07" in document.filename or "pull request" in text or " pr" in text or "贡献" in text


def _is_resume_document(document: GeneratedDocument) -> bool:
    text = f"{document.filename}\n{document.title}\n{document.content}".lower()
    return "06" in document.filename or "resume" in text or "简历" in text


def _unique(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
