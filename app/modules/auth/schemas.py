"""Public authentication request and response contracts."""
from pydantic import BaseModel, Field, field_validator


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()


class AuthUser(BaseModel):
    id: int
    username: str
    csrf_token: str


class LogoutResult(BaseModel):
    ok: bool = True
