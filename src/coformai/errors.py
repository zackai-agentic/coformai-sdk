"""HTTP, transport, and protocol errors shared by both Coform clients.

Status errors retain server validation details and request identifiers. Credentials
are never included in SDK error messages. Mutating requests are never retried.
"""

from __future__ import annotations

from typing import Any

import httpx


class CoformError(Exception):
    """Base exception for SDK transport and protocol failures."""

    operation_id: str | None = None


class APIStatusError(CoformError):
    """A server returned an unsuccessful HTTP status.

    Attributes:
        status_code: HTTP response status.
        body: Parsed server error, or its textual body.
        request_id: Server request/correlation identifier, if available.
        retry_after: Server Retry-After header; the SDK does not retry automatically.
    """

    status_code: int
    body: Any
    request_id: str | None
    retry_after: str | None

    def __init__(self, response: httpx.Response) -> None:
        """Capture diagnostics without copying request credentials.

        Args:
            response: Unsuccessful response whose body has already been read.

        Returns:
            None. Stores status, body, request ID, and Retry-After on this exception.
        """
        self.status_code = response.status_code
        try:
            self.body: Any = response.json()
        except ValueError:
            self.body = response.text
        self.request_id = response.headers.get("x-request-id")
        self.retry_after = response.headers.get("retry-after")
        super().__init__(f"Coform API returned HTTP {self.status_code}")


class AuthenticationError(APIStatusError):
    """HTTP 401: missing, invalid, expired, revoked, or IP-restricted credentials."""


class PermissionDeniedError(APIStatusError):
    """HTTP 403: a selected API-key permission is missing."""


class NotFoundError(APIStatusError):
    """HTTP 404: a resource is absent or outside the caller's organization."""


class ConflictError(APIStatusError):
    """HTTP 409: session ownership, active execution, or another server conflict."""


class ValidationError(APIStatusError):
    """HTTP 400/422: inspect body for field or graph-operation validation details."""


class RateLimitError(APIStatusError):
    """HTTP 429: request rate or token budget is exhausted."""


class APIConnectionError(CoformError):
    """A connection failed; a mutation's outcome may be indeterminate."""

    def __init__(self, message: str, *, operation_id: str | None = None) -> None:
        super().__init__(message)
        self.operation_id = operation_id


class APITimeoutError(APIConnectionError):
    """A configured timeout expired; check session status before replaying work."""


class StreamProtocolError(CoformError):
    """An invocation stream contains invalid JSON or an invalid event envelope."""


def check_status(response: httpx.Response, *, operation_id: str | None = None) -> None:
    """Validate HTTP success; callers must read a streaming error body first.

    Args:
        response: HTTP response containing status and readable diagnostics.
        operation_id: UUID sent with a dashboard write, when applicable.

    Returns:
        None when the response is successful.

    Raises:
        APIStatusError: HTTP failure; known statuses use their specific subclasses.
    """
    if response.is_success:
        return
    error_type = {
        400: ValidationError,
        401: AuthenticationError,
        403: PermissionDeniedError,
        404: NotFoundError,
        409: ConflictError,
        422: ValidationError,
        429: RateLimitError,
    }.get(response.status_code, APIStatusError)
    error = error_type(response)
    error.operation_id = operation_id
    raise error
