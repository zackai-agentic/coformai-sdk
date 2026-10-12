"""Single-use invocation streams with explicit cleanup and NDJSON decoding."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
from pydantic import ValidationError as PydanticValidationError

from .errors import (
    APIConnectionError,
    APITimeoutError,
    CoformError,
    StreamProtocolError,
    check_status,
)
from .models import InvocationEvent, InvocationResult, StreamMode


def _event(line: str) -> InvocationEvent:
    try:
        return InvocationEvent.model_validate(json.loads(line))
    except (ValueError, PydanticValidationError) as exc:
        raise StreamProtocolError("Invalid JSON-line invocation event") from exc


class InvocationStream:
    """A single-use sync stream; use a with block when stopping iteration early.

    Iteration yields all events, including failures and approvals. collect()
    returns an InvocationResult. HTTP errors raise SDK status exceptions; network
    interruptions raise transport exceptions. partial_result retains events read
    before an interruption. Closing the HTTP response does not guarantee that
    server execution was cancelled.

    Args:
        client: Authenticated HTTPX client; normally supplied by Coform.
        url: Complete core endpoint URL, already joined to its configured root.
        payload: Core invocation request fields.
        mode: Response text framing mode; every mode still uses NDJSON.
        timeout: HTTPX connect/write/pool/read timeout configuration.

    Attributes:
        partial_result: Events and output consumed so far, including on interruption.

    Required permission: inference:execute. Construction is local; entering or
    iterating sends exactly one invocation POST.
    """

    def __init__(
        self,
        client: httpx.Client,
        url: str,
        payload: dict[str, Any],
        mode: StreamMode,
        timeout: httpx.Timeout,
    ) -> None:
        """Initialize a lazy stream; the POST begins on entry or first iteration."""
        self._client, self._url, self._payload = client, url, payload
        self._mode, self._timeout = mode, timeout
        self._response: httpx.Response | None = None
        self._used = False
        self.partial_result = InvocationResult()

    def __enter__(self) -> InvocationStream:
        """Open the response and validate HTTP status before yielding events."""
        if self._response is not None:
            return self
        if self._used:
            raise CoformError(
                "Invocation streams are single-use; this request will not be replayed"
            )
        self._used = True
        try:
            request = self._client.build_request(
                "POST", self._url, json=self._payload, timeout=self._timeout
            )
            self._response = self._client.send(request, stream=True)
            if not self._response.is_success:
                self._response.read()
            check_status(self._response)
        except httpx.TimeoutException as exc:
            self.close()
            raise APITimeoutError("Invocation connection timed out") from exc
        except httpx.RequestError as exc:
            self.close()
            raise APIConnectionError("Invocation connection failed") from exc
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, *args: object) -> None:
        """Close the response even when the consumer exits early or raises."""
        self.close()

    def __iter__(self) -> Iterator[InvocationEvent]:
        """Decode UTF-8 JSON lines; chunks and event boundaries are independent."""
        self.__enter__()
        assert self._response is not None
        try:
            for line in self._response.iter_lines():
                if line.strip():
                    event = _event(line)
                    self.partial_result.add(event, self._mode)
                    yield event
        except httpx.TimeoutException as exc:
            raise APITimeoutError("Invocation stream timed out; reconcile session status") from exc
        except httpx.RequestError as exc:
            raise APIConnectionError(
                "Invocation stream interrupted; reconcile session status"
            ) from exc
        finally:
            self.close()

    def collect(self) -> InvocationResult:
        """Consume and close the stream, returning an explicit execution outcome.

        Returns:
            Collected events and output. Missing terminal events remain indeterminate.

        Raises:
            CoformError: The stream is already consumed or explicitly closed.
            APIStatusError: The core rejected the invocation request.
            APIConnectionError: Transport interruption; partial_result remains available.
            StreamProtocolError: An event is malformed.
        """
        for _ in self:
            pass
        return self.partial_result

    def close(self) -> None:
        """Close an open response without replaying the request or cancelling server work."""
        self._used = True
        if self._response is not None:
            self._response.close()
            self._response = None


class AsyncInvocationStream:
    """Single-use async invocation response, supporting async with and async for.

    Args:
        client: Authenticated HTTPX async client, normally supplied by AsyncCoform.
        url: Complete core endpoint URL inside its configured root.
        payload: Core invocation request fields.
        mode: Text framing mode; every mode still uses NDJSON.
        timeout: HTTPX timeout configuration, including the stream read timeout.

    Attributes:
        partial_result: Parsed events and output consumed before any interruption.

    Requires inference:execute. Construction makes no request; context entry or
    iteration sends one POST. Early closure releases the response and does not
    guarantee server cancellation. Requests are never replayed automatically.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, Any],
        mode: StreamMode,
        timeout: httpx.Timeout,
    ) -> None:
        """Initialize a lazy async stream with a retained partial_result."""
        self._client, self._url, self._payload = client, url, payload
        self._mode, self._timeout = mode, timeout
        self._response: httpx.Response | None = None
        self._used = False
        self.partial_result = InvocationResult()

    async def __aenter__(self) -> AsyncInvocationStream:
        """Open the response and check HTTP status before reading events."""
        if self._response is not None:
            return self
        if self._used:
            raise CoformError(
                "Invocation streams are single-use; this request will not be replayed"
            )
        self._used = True
        try:
            request = self._client.build_request(
                "POST", self._url, json=self._payload, timeout=self._timeout
            )
            self._response = await self._client.send(request, stream=True)
            if not self._response.is_success:
                await self._response.aread()
            check_status(self._response)
        except httpx.TimeoutException as exc:
            await self.aclose()
            raise APITimeoutError("Invocation connection timed out") from exc
        except httpx.RequestError as exc:
            await self.aclose()
            raise APIConnectionError("Invocation connection failed") from exc
        except BaseException:
            await self.aclose()
            raise
        return self

    async def __aexit__(self, *args: object) -> None:
        """Close the response on normal exit, error, or async cancellation."""
        await self.aclose()

    async def __aiter__(self) -> AsyncIterator[InvocationEvent]:
        """Yield decoded events, retaining forward-compatible fields and result values."""
        await self.__aenter__()
        assert self._response is not None
        try:
            async for line in self._response.aiter_lines():
                if line.strip():
                    event = _event(line)
                    self.partial_result.add(event, self._mode)
                    yield event
        except httpx.TimeoutException as exc:
            raise APITimeoutError("Invocation stream timed out; reconcile session status") from exc
        except httpx.RequestError as exc:
            raise APIConnectionError(
                "Invocation stream interrupted; reconcile session status"
            ) from exc
        finally:
            await self.aclose()

    async def collect(self) -> InvocationResult:
        """Consume and close the stream; await to obtain its terminal outcome.

        Returns:
            Collected events and output, or indeterminate when no terminal event arrives.

        Raises:
            CoformError: The stream was consumed or explicitly closed.
            APIStatusError: The core rejected the request.
            APIConnectionError: Transport interruption; partial_result remains available.
            StreamProtocolError: The server sends a malformed event.
        """
        async for _ in self:
            pass
        return self.partial_result

    async def aclose(self) -> None:
        """Close the HTTP response without claiming server execution has stopped."""
        self._used = True
        if self._response is not None:
            await self._response.aclose()
            self._response = None
