from pydantic import BaseModel


class CreateConversationRequest(BaseModel):
    title: str | None = None
