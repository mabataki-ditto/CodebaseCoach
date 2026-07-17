from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.prompts import REAL_DOCUMENT_PROMPTS
from app.agent_graph.context import AnalysisRuntimeContext
from app.agent_graph.document_state import DocumentSubgraphOutput, DocumentSubgraphState
from app.agent_graph.nodes.generate_document import make_generate_document_node
from app.agent_graph.nodes.merge_documents import merge_documents


def add_document_generation_nodes(graph: StateGraph) -> list[str]:
    """Add the fixed parallel document nodes and return their node names."""
    document_nodes: list[str] = []
    for index, prompt in enumerate(REAL_DOCUMENT_PROMPTS):
        node_name = f"generate_document_{index + 1:02d}"
        document_nodes.append(node_name)
        graph.add_node(node_name, make_generate_document_node(index, prompt))

    graph.add_node("merge_documents", merge_documents)
    graph.add_edge(document_nodes, "merge_documents")
    return document_nodes


def build_document_generation_subgraph() -> CompiledStateGraph:
    """Build the seven fixed document branches and their stable merge node."""
    graph = StateGraph(
        DocumentSubgraphState,
        context_schema=AnalysisRuntimeContext,
        output_schema=DocumentSubgraphOutput,
    )
    document_nodes = add_document_generation_nodes(graph)
    for node_name in document_nodes:
        graph.add_edge(START, node_name)

    graph.add_edge("merge_documents", END)
    return graph.compile()
