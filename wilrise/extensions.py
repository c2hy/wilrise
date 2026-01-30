"""Extension point contracts: parsing, response building, exception mapping, logging."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from starlette.requests import Request
from starlette.responses import Response

from wilrise.context import RpcContext, RpcRequestId


@dataclass(frozen=True)
class ParsedRequest:
    """Contract for RequestParser.parse() result. Do not construct outside parser.

    Framework expects these fields for dispatch; changing shape breaks core.
    """

    method: str
    params: dict[str, Any] | list[Any] | None
    id: RpcRequestId
    is_notification: bool


@runtime_checkable
class RequestParser(Protocol):
    """Extension point: parse raw request body into a ParsedRequest."""

    def parse(
        self,
        body: dict[str, Any],
        request: Request,
    ) -> tuple[ParsedRequest | None, dict[str, Any] | None]:
        """Parse and validate a single request body.

        Returns (parsed_request, invalid_data):
        - (ParsedRequest, None): valid request.
        - (None, None): invalid; framework responds Invalid Request (body.get("id")).
        - (None, data): invalid with optional data; framework responds with data=data.
        """
        ...


@runtime_checkable
class ResponseBuilder(Protocol):
    """Extension point: build JSON-RPC success and error response dicts."""

    def build_result(self, result: Any, req_id: RpcRequestId) -> dict[str, Any]:
        """Build the success response object (jsonrpc, result, id)."""
        ...

    def build_error(
        self,
        code: int,
        message: str,
        req_id: RpcRequestId,
        *,
        data: Any = None,
    ) -> dict[str, Any]:
        """Build the error response object (jsonrpc, error, id)."""
        ...


@runtime_checkable
class ExceptionMapper(Protocol):
    """Extension point: map uncaught exceptions to (code, message, data)."""

    def map_exception(
        self,
        exc: Exception,
        context: RpcContext,
    ) -> tuple[int, str, Any] | None:
        """Map exception to (code, message, data). Return None for framework default."""
        ...


RequestLogger = Callable[
    [RpcContext, float, Response | None, BaseException | None],
    None | Awaitable[None],
]
"""Extension point: log request completion. (context, duration_ms, response, error)."""
