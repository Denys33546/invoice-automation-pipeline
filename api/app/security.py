"""Optional API key check for the /extract endpoint."""

import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.config import SettingsDep


def require_api_key(
    settings: SettingsDep,
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Does nothing when no key is configured; otherwise the X-API-Key header must match."""
    if not settings.api_key:
        return
    # compare bytes: compare_digest raises TypeError for non-ASCII str
    if x_api_key is None or not hmac.compare_digest(x_api_key.encode(), settings.api_key.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
