from pydantic import BaseModel


class ResearchContext(BaseModel):
    description: str
    steps: list[str]
