from pydantic import BaseModel, Field


class RepoRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)


class RepoParseResponse(BaseModel):
    owner: str
    repo: str
    repo_url: str


class FileTreeNode(BaseModel):
    name: str
    path: str
    type: str
    children: list["FileTreeNode"] = Field(default_factory=list)


class BasicFileSummary(BaseModel):
    path: str
    file_type: str
    size: int
    content_preview: str
    truncated: bool


class RepoScanResponse(RepoParseResponse):
    file_tree: list[FileTreeNode]
    basic_files: list[BasicFileSummary]
