from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent_graph.context import AnalysisRuntimeContext
from app.agent_graph.document_state import DocumentSubgraphState
from app.agent_graph.document_subgraph import (
    add_document_generation_nodes,
    build_document_generation_subgraph,
)
from app.agent_graph.nodes.build_analysis_context import build_analysis_context
from app.agent_graph.nodes.build_context_quality_report import build_context_quality_report
from app.agent_graph.nodes.clone_repo import clone_repo
from app.agent_graph.nodes.fetch_github_mcp_context import fetch_github_mcp_context
from app.agent_graph.nodes.evaluate_documents import (
    evaluate_documents,
    prepare_quality_retry,
    route_after_quality,
)
from app.agent_graph.nodes.parse_repo import parse_repo
from app.agent_graph.nodes.prepare_repository_recovery import prepare_repository_recovery
from app.agent_graph.nodes.scan_repo import scan_repo
from app.agent_graph.nodes.select_core_files import select_core_files
from app.agent_graph.state import AnalysisState


def build_analysis_graph(
    *,
    include_document_generation: bool = False,
    include_quality_loop: bool = False,
    checkpointer: BaseCheckpointSaver | None = None,
    selective_quality_retry: bool = False,
) -> CompiledStateGraph:
    """Build the opt-in analysis graph through the requested migration phase."""
    persistent_documents = selective_quality_retry or (
        checkpointer is not None and (include_document_generation or include_quality_loop)
    )
    if persistent_documents:
        graph = StateGraph(
            DocumentSubgraphState,
            context_schema=AnalysisRuntimeContext,
            output_schema=AnalysisState,
        )
    else:
        graph = StateGraph(AnalysisState, context_schema=AnalysisRuntimeContext)
    graph.add_node("parse_repo", parse_repo)
    graph.add_node("clone_repo", clone_repo)
    graph.add_node("prepare_repository_recovery", prepare_repository_recovery)
    graph.add_node("scan_repo", scan_repo)
    graph.add_node("select_core_files", select_core_files)
    graph.add_node("build_context_quality_report", build_context_quality_report)
    graph.add_node("build_analysis_context", build_analysis_context)
    graph.add_node("fetch_github_mcp_context", fetch_github_mcp_context)
    graph.add_edge(START, "parse_repo")
    graph.add_edge("parse_repo", "clone_repo")
    graph.add_edge("clone_repo", "prepare_repository_recovery")
    graph.add_edge("prepare_repository_recovery", "scan_repo")
    graph.add_edge("scan_repo", "select_core_files")
    graph.add_edge("select_core_files", "build_context_quality_report")
    graph.add_edge("build_context_quality_report", "build_analysis_context")
    graph.add_edge("build_analysis_context", "fetch_github_mcp_context")
    if not include_document_generation and not include_quality_loop:
        graph.add_edge("fetch_github_mcp_context", END)
        return graph.compile(checkpointer=checkpointer)

    if persistent_documents:
        document_nodes = add_document_generation_nodes(graph)
        for node_name in document_nodes:
            graph.add_edge("fetch_github_mcp_context", node_name)
        generation_exit = "merge_documents"
    else:
        graph.add_node("generate_documents", build_document_generation_subgraph())
        graph.add_edge("fetch_github_mcp_context", "generate_documents")
        document_nodes = []
        generation_exit = "generate_documents"
    if not include_quality_loop:
        graph.add_edge(generation_exit, END)
        return graph.compile(checkpointer=checkpointer)

    graph.add_node("evaluate_documents", evaluate_documents)
    graph.add_node("prepare_quality_retry", prepare_quality_retry)
    graph.add_edge(generation_exit, "evaluate_documents")
    graph.add_conditional_edges(
        "evaluate_documents",
        route_after_quality,
        {"retry": "prepare_quality_retry", "end": END},
    )
    if persistent_documents:
        for node_name in document_nodes:
            graph.add_edge("prepare_quality_retry", node_name)
    else:
        graph.add_edge("prepare_quality_retry", "generate_documents")
    return graph.compile(checkpointer=checkpointer)
