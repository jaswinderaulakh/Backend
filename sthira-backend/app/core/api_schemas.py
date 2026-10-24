"""
Request/response shapes for users, login, buildings and health check.

These are NOT in schemas.py on purpose: schemas.py is a shared file and
holds only the data passed between analysis modules.
"""
from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=50)]


class RegisterRequest(BaseModel):
    username: Username                     # login name, 3-50 characters
    password: str = Field(min_length=6)    # at least 6 characters (and at most 72 bytes)

    @field_validator("password")
    @classmethod
    def password_not_too_long(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password is too long (72 bytes at most)")
        return value


class UserOut(BaseModel):
    id: int                                # user number
    username: str                          # login name
    created_at: datetime                   # when the account was made (UTC)


class TokenResponse(BaseModel):
    access_token: str                      # the login token: send it with every later request
    token_type: str = "bearer"


class BuildingCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]  # building name
    latitude: float = Field(ge=-90, le=90)      # map position, north-south
    longitude: float = Field(ge=-180, le=180)   # map position, east-west


class BuildingOut(BaseModel):
    id: int                                # building number
    name: str                              # building name
    latitude: float                        # map position, north-south
    longitude: float                       # map position, east-west
    created_at: datetime                   # when it was added (UTC)


class HealthResponse(BaseModel):
    status: str                            # "ok" when the server is running
    version: str                           # backend version
    database: Optional[str] = None         # "ok" when the database answers
