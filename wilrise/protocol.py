"""JSON-RPC 2.0 protocol layer: request/response types and build/parse helpers."""

from dataclasses import dataclass
from typing import Any, cast

from wilrise.context import RpcRequestId


@dataclass(frozen=True)
class JsonRpcRequest:
    """Parsed single JSON-RPC request."""

    method: str
    params: dict[str, Any] | list[Any] | None
    id: RpcRequestId  # Echoed in response; only used when not is_notification
    is_notification: bool  # True when "id" was omitted (no response)


def parse_single_request(
    body: dict[str, Any],
) -> tuple[JsonRpcRequest | None, dict[str, Any] | None]:
    """Parse and validate a single request body.

    Returns (parsed_request, invalid_data):
    - (JsonRpcRequest, None): valid request.
    - (None, None): invalid request; caller should respond with Invalid Request
      using body.get("id").
    - (None, data): invalid request with optional data (e.g. reserved_method_name);
      caller should respond with Invalid Request with data=data.
    """
    if body.get("jsonrpc") != "2.0":
        return None, None
    method = body.get("method")
    if not method or not isinstance(method, str):
        return None, None
    if method.startswith("rpc."):
        return None, {"method": method, "reason": "reserved_method_name"}
    params_raw = body.get("params")
    if params_raw is not None and not isinstance(params_raw, (list, dict)):
        return None, None
    params: dict[str, Any] | list[Any] | None = cast(
        dict[str, Any] | list[Any] | None, params_raw
    )
    is_notification = "id" not in body
    req_id = body.get("id") if not is_notification else None
    return (
        JsonRpcRequest(
            method=method, params=params, id=req_id, is_notification=is_notification
        ),
        None,
    )


def build_error(
    code: int,
    message: str,
    req_id: RpcRequestId,
    *,
    data: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC error response object (§5.1)."""
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "error": err, "id": req_id}


def build_result(result: Any, req_id: RpcRequestId) -> dict[str, Any]:
    """Build a JSON-RPC success response object."""
    return {"jsonrpc": "2.0", "result": result, "id": req_id}
