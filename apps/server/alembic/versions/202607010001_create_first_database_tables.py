"""create first database tables

Revision ID: 202607010001
Revises:
Create Date: 2026-07-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607010001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("repo_url", sa.String(length=512), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("repo", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repo_url"),
    )
    op.create_index(op.f("ix_repositories_repo_url"), "repositories", ["repo_url"], unique=False)

    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("repository_id", sa.String(length=64), nullable=True),
        sa.Column("repo_url", sa.String(length=512), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("repo", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mock_mode", sa.Boolean(), nullable=False),
        sa.Column("llm_provider", sa.String(length=255), nullable=False),
        sa.Column("llm_model", sa.String(length=255), nullable=False),
        sa.Column("docs_dir", sa.String(length=1024), nullable=False),
        sa.Column("core_files_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analysis_jobs_created_at"), "analysis_jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_analysis_jobs_repository_id"), "analysis_jobs", ["repository_id"], unique=False)
    op.create_index(op.f("ix_analysis_jobs_status"), "analysis_jobs", ["status"], unique=False)

    op.create_table(
        "analysis_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "sequence", name="uq_analysis_events_job_sequence"),
    )
    op.create_index(op.f("ix_analysis_events_job_id"), "analysis_events", ["job_id"], unique=False)

    op.create_table(
        "analysis_artifacts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "artifact_type", name="uq_analysis_artifacts_job_type"),
    )
    op.create_index(op.f("ix_analysis_artifacts_job_id"), "analysis_artifacts", ["job_id"], unique=False)

    op.create_table(
        "generated_documents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("doc_type", sa.String(length=128), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generated_documents_job_id"), "generated_documents", ["job_id"], unique=False)

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("started_at", sa.String(length=64), nullable=True),
        sa.Column("ended_at", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_steps_job_id"), "agent_steps", ["job_id"], unique=False)
    op.create_index(op.f("ix_agent_steps_step_id"), "agent_steps", ["step_id"], unique=False)

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("step_id", sa.String(length=64), nullable=True),
        sa.Column("tool_provider", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_summary", sa.Text(), nullable=False),
        sa.Column("output_summary", sa.Text(), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("related_files_json", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tool_calls_created_at"), "tool_calls", ["created_at"], unique=False)
    op.create_index(op.f("ix_tool_calls_job_id"), "tool_calls", ["job_id"], unique=False)
    op.create_index(op.f("ix_tool_calls_step_id"), "tool_calls", ["step_id"], unique=False)
    op.create_index(op.f("ix_tool_calls_tool_provider"), "tool_calls", ["tool_provider"], unique=False)

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_type", sa.String(length=255), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_calls_job_id"), "llm_calls", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_calls_job_id"), table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index(op.f("ix_tool_calls_tool_provider"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_step_id"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_job_id"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_created_at"), table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_index(op.f("ix_agent_steps_step_id"), table_name="agent_steps")
    op.drop_index(op.f("ix_agent_steps_job_id"), table_name="agent_steps")
    op.drop_table("agent_steps")
    op.drop_index(op.f("ix_generated_documents_job_id"), table_name="generated_documents")
    op.drop_table("generated_documents")
    op.drop_index(op.f("ix_analysis_artifacts_job_id"), table_name="analysis_artifacts")
    op.drop_table("analysis_artifacts")
    op.drop_index(op.f("ix_analysis_events_job_id"), table_name="analysis_events")
    op.drop_table("analysis_events")
    op.drop_index(op.f("ix_analysis_jobs_status"), table_name="analysis_jobs")
    op.drop_index(op.f("ix_analysis_jobs_repository_id"), table_name="analysis_jobs")
    op.drop_index(op.f("ix_analysis_jobs_created_at"), table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_index(op.f("ix_repositories_repo_url"), table_name="repositories")
    op.drop_table("repositories")
