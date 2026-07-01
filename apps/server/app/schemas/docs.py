from app.schemas.agent import GeneratedDocument

from pydantic import BaseModel


class DocsResponse(BaseModel):
    history_id: str
    docs_dir: str
    documents: list[GeneratedDocument]
