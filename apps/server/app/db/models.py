from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RepositoryRow(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repo_url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    repo: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    analysis_jobs: Mapped[list["AnalysisJobRow"]] = relationship(back_populates="repository")


class AnalysisJobRow(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("repositories.id"), nullable=True, index=True)
    repo_url: Mapped[str] = mapped_column(String(512), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    repo: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    mock_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    llm_provider: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    llm_model: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    docs_dir: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    core_files_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    repository: Mapped[RepositoryRow | None] = relationship(back_populates="analysis_jobs")
    events: Mapped[list["AnalysisEventRow"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    artifacts: Mapped[list["AnalysisArtifactRow"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    generated_documents: Mapped[list["GeneratedDocumentRow"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    agent_steps: Mapped[list["AgentStepRow"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    tool_calls: Mapped[list["ToolCallRow"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    llm_calls: Mapped[list["LlmCallRow"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class AnalysisEventRow(Base):
    __tablename__ = "analysis_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence", name="uq_analysis_events_job_sequence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

    job: Mapped[AnalysisJobRow] = relationship(back_populates="events")


class AnalysisArtifactRow(Base):
    __tablename__ = "analysis_artifacts"
    __table_args__ = (UniqueConstraint("job_id", "artifact_type", name="uq_analysis_artifacts_job_type"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[object] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    job: Mapped[AnalysisJobRow] = relationship(back_populates="artifacts")


class GeneratedDocumentRow(Base):
    __tablename__ = "generated_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    job: Mapped[AnalysisJobRow] = relationship(back_populates="generated_documents")


class AgentStepRow(Base):
    __tablename__ = "agent_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    job: Mapped[AnalysisJobRow] = relationship(back_populates="agent_steps")


class ToolCallRow(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    step_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tool_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="builtin", index=True)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    related_files_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    job: Mapped[AnalysisJobRow] = relationship(back_populates="tool_calls")


class LlmCallRow(Base):
    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    prompt_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

    job: Mapped[AnalysisJobRow] = relationship(back_populates="llm_calls")
