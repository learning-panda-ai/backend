from pydantic import BaseModel

from app.schemas.user import UserOut


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenWithUser(TokenResponse):
    user: UserOut
