"""Request correlation middleware."""

from collections.abc import Awaitable, Callable
from uuid import uuid4
import re

from fastapi import Request, Response


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    submitted_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        submitted_request_id
        if _REQUEST_ID_PATTERN.fullmatch(submitted_request_id)
        else str(uuid4())
    )
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
