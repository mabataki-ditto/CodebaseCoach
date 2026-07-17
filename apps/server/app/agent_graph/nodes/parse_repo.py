from app.agent_graph.state import AnalysisState
from app.agent_graph.stage_adapter import GraphStageAdapter
from app.services.repo_parser import parse_github_repo_url


def parse_repo(state: AnalysisState) -> AnalysisState:
    """Parse and normalize the repository URL using the existing service."""
    adapter = GraphStageAdapter(state)
    parsed_repo = adapter.run(
        key="parse_repo_url",
        title="Parse GitHub URL",
        description="Run workflow stage",
        tool_name="parse_github_repo_url",
        input_summary=state["repo_url"],
        input_payload={"repo_url": state["repo_url"]},
        action=lambda: parse_github_repo_url(state["repo_url"]),
        output_summary=lambda result: f"{result.owner}/{result.repo}",
        output_payload=lambda result: {
            "owner": result.owner,
            "repo": result.repo,
            "repo_url": result.repo_url,
        },
    )
    return {"parsed_repo": parsed_repo, **adapter.state_update()}
