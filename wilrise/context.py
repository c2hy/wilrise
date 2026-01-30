"""RPC context: first-class context object for the current JSON-RPC call."""

from dataclasses import dataclass

from starlette.requests import Request

# JSON-RPC 2.0 §4: id MAY be String, Number, or Null; omitted for notifications.
RpcRequestId = str | int | float | None


@dataclass(frozen=True)
class RpcContext:
    """Per-request context set by the framework. Immutable.

    Available in hooks via request.state.rpc_context;
    in methods via Use(get_rpc_context). Do not mutate or construct outside framework.
    """

    method: str
    request_id: RpcRequestId
    http_request_id: str
    is_notification: bool
    request: Request


def get_rpc_context(request: Request) -> RpcContext | None:
    """Return request.state.rpc_context if set, else None. Use only inside RPC scope."""
    return getattr(request.state, "rpc_context", None)
