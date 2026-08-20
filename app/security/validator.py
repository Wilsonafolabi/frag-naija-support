import re
from pydantic import BaseModel, Field, field_validator

class SecureChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(None, max_length=100, pattern=r"^[a-zA-Z0-9\-]+$")
    user_id: str | None = Field(None, max_length=100, pattern=r"^[a-zA-Z0-9\-]+$")

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        # Remove control characters (prevents terminal/log injection)
        v = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', v)
        return v.strip()