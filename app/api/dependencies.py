from fastapi import Header

from rag.errors import UnauthorizedError


async def get_api_key(authorization: str | None = Header(default=None)) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    return authorization.removeprefix("Bearer ").strip()
