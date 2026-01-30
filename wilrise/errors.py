"""JSON-RPC error codes and application error type.

Error codes follow JSON-RPC 2.0 §5.1:
- -32700 .. -32600: reserved for protocol / server
- -32099 .. -32000: reserved for server implementation (application errors)
"""

from typing import Any

# Standard JSON-RPC 2.0 error codes (§5.1)
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Application-defined error code range (§5.1): -32099 to -32000
# Use RpcError(code=..., message=..., data=...) for application errors.


class RpcError(Exception):
    """Application-level error. code must be in -32099..-32000 (enforced in __init__).

    Do not use for protocol errors (-32700..-32600); reserved for implementation.
    """

    def __init__(
        self,
        code: int,
        message: str,
        *,
        data: Any = None,
    ) -> None:
        if not (-32099 <= code <= -32000):
            raise ValueError(
                f"Application error code must be in -32099..-32000, got {code}"
            )
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)
