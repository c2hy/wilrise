"""Protocol layer tests — covers JSON-RPC 2.0 parsing and response building.

Tests cover:
  - parse_single_request() validation logic
  - build_error() and build_result() response building
  - JsonRpcRequest dataclass
  - Reserved method names
  - Notification detection
"""

import dataclasses

import pytest
from wilrise.protocol import (
    JsonRpcRequest,
    build_error,
    build_result,
    parse_single_request,
)


class TestParseSingleRequest:
    """Test parse_single_request() validation and parsing logic."""

    def test_valid_request_with_dict_params(self) -> None:
        """Valid request with named params returns JsonRpcRequest."""
        body = {
            "jsonrpc": "2.0",
            "method": "add",
            "params": {"a": 1, "b": 2},
            "id": 1,
        }
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert invalid_data is None
        assert parsed.method == "add"
        assert parsed.params == {"a": 1, "b": 2}
        assert parsed.id == 1
        assert parsed.is_notification is False

    def test_valid_request_with_list_params(self) -> None:
        """Valid request with positional params returns JsonRpcRequest."""
        body = {"jsonrpc": "2.0", "method": "add", "params": [1, 2], "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert invalid_data is None
        assert parsed.method == "add"
        assert parsed.params == [1, 2]
        assert parsed.id == 1
        assert parsed.is_notification is False

    def test_valid_request_without_params(self) -> None:
        """Valid request without params returns JsonRpcRequest with None params."""
        body = {"jsonrpc": "2.0", "method": "ping", "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert invalid_data is None
        assert parsed.method == "ping"
        assert parsed.params is None
        assert parsed.id == 1
        assert parsed.is_notification is False

    def test_notification_request(self) -> None:
        """Request without 'id' is a notification."""
        body = {"jsonrpc": "2.0", "method": "ping"}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert invalid_data is None
        assert parsed.method == "ping"
        assert parsed.id is None
        assert parsed.is_notification is True

    def test_notification_with_params(self) -> None:
        """Notification can have params."""
        body = {"jsonrpc": "2.0", "method": "log", "params": {"msg": "hello"}}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert invalid_data is None
        assert parsed.method == "log"
        assert parsed.params == {"msg": "hello"}
        assert parsed.id is None
        assert parsed.is_notification is True

    def test_missing_jsonrpc_field(self) -> None:
        """Missing jsonrpc field returns None, None."""
        body = {"method": "add", "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is None
        assert invalid_data is None

    def test_wrong_jsonrpc_version(self) -> None:
        """jsonrpc version not '2.0' returns None, None."""
        body = {"jsonrpc": "1.0", "method": "add", "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is None
        assert invalid_data is None

    def test_missing_method_field(self) -> None:
        """Missing method field returns None, None."""
        body = {"jsonrpc": "2.0", "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is None
        assert invalid_data is None

    def test_method_not_string(self) -> None:
        """Method not a string returns None, None."""
        body = {"jsonrpc": "2.0", "method": 123, "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is None
        assert invalid_data is None

    def test_method_empty_string(self) -> None:
        """Empty method string returns None, None."""
        body = {"jsonrpc": "2.0", "method": "", "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is None
        assert invalid_data is None

    def test_reserved_method_name(self) -> None:
        """Method starting with 'rpc.' returns None with data."""
        body = {"jsonrpc": "2.0", "method": "rpc.discover", "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is None
        assert invalid_data is not None
        assert invalid_data["method"] == "rpc.discover"
        assert invalid_data["reason"] == "reserved_method_name"

    def test_reserved_method_name_case_sensitive(self) -> None:
        """'RPC.' (uppercase) is not reserved."""
        body = {"jsonrpc": "2.0", "method": "RPC.test", "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert invalid_data is None
        assert parsed.method == "RPC.test"

    def test_params_not_object_or_array(self) -> None:
        """params is a scalar (not dict/list) returns None, None."""
        body = {"jsonrpc": "2.0", "method": "add", "params": 42, "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is None
        assert invalid_data is None

    def test_params_boolean(self) -> None:
        """params as boolean returns None, None."""
        body = {"jsonrpc": "2.0", "method": "add", "params": True, "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is None
        assert invalid_data is None

    def test_params_null(self) -> None:
        """params as null is treated as None (valid)."""
        body = {"jsonrpc": "2.0", "method": "add", "params": None, "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert invalid_data is None
        assert parsed.params is None

    def test_id_string(self) -> None:
        """id can be a string."""
        body = {"jsonrpc": "2.0", "method": "add", "id": "abc123"}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert parsed.id == "abc123"

    def test_id_float(self) -> None:
        """id can be a float."""
        body = {"jsonrpc": "2.0", "method": "add", "id": 1.5}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert parsed.id == 1.5

    def test_id_null(self) -> None:
        """id: null is valid and not a notification."""
        body = {"jsonrpc": "2.0", "method": "add", "id": None}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert parsed.id is None
        assert parsed.is_notification is False

    def test_empty_params_dict(self) -> None:
        """Empty params dict is valid."""
        body = {"jsonrpc": "2.0", "method": "add", "params": {}, "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert parsed.params == {}

    def test_empty_params_list(self) -> None:
        """Empty params list is valid."""
        body = {"jsonrpc": "2.0", "method": "add", "params": [], "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert parsed.params == []

    def test_nested_params_dict(self) -> None:
        """Nested dict params are preserved."""
        body = {
            "jsonrpc": "2.0",
            "method": "create",
            "params": {"user": {"name": "Alice", "age": 30}},
            "id": 1,
        }
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert parsed.params == {"user": {"name": "Alice", "age": 30}}

    def test_nested_params_list(self) -> None:
        """Nested list params are preserved."""
        body = {
            "jsonrpc": "2.0",
            "method": "batch",
            "params": [[1, 2], [3, 4]],
            "id": 1,
        }
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert parsed.params == [[1, 2], [3, 4]]

    def test_method_with_dots(self) -> None:
        """Method names can contain dots (except rpc. prefix)."""
        body = {"jsonrpc": "2.0", "method": "user.getById", "id": 1}
        parsed, invalid_data = parse_single_request(body)
        assert parsed is not None
        assert parsed.method == "user.getById"


class TestBuildError:
    """Test build_error() response building."""

    def test_build_error_without_data(self) -> None:
        """Build error without data field."""
        result = build_error(-32600, "Invalid Request", 1)
        assert result == {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Invalid Request"},
            "id": 1,
        }

    def test_build_error_with_data(self) -> None:
        """Build error with data field."""
        result = build_error(
            -32602, "Invalid params", 1, data={"validation_errors": []}
        )
        assert result == {
            "jsonrpc": "2.0",
            "error": {
                "code": -32602,
                "message": "Invalid params",
                "data": {"validation_errors": []},
            },
            "id": 1,
        }

    def test_build_error_with_null_id(self) -> None:
        """Build error with id: null."""
        result = build_error(-32600, "Invalid Request", None)
        assert result == {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Invalid Request"},
            "id": None,
        }

    def test_build_error_with_string_id(self) -> None:
        """Build error with string id."""
        result = build_error(-32601, "Method not found", "abc")
        assert result == {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Method not found"},
            "id": "abc",
        }

    def test_build_error_with_complex_data(self) -> None:
        """Build error with complex nested data."""
        data = {
            "type": "ValidationError",
            "details": [{"field": "email", "message": "invalid format"}],
        }
        result = build_error(-32602, "Invalid params", 1, data=data)
        assert result["error"]["data"] == data

    def test_build_error_standard_codes(self) -> None:
        """Build error with all standard JSON-RPC error codes."""
        codes = [-32700, -32600, -32601, -32602, -32603]
        for code in codes:
            result = build_error(code, "test", 1)
            assert result["error"]["code"] == code

    def test_build_error_application_codes(self) -> None:
        """Build error with application error codes."""
        codes = [-32000, -32050, -32099]
        for code in codes:
            result = build_error(code, "test", 1)
            assert result["error"]["code"] == code


class TestBuildResult:
    """Test build_result() response building."""

    def test_build_result_with_string(self) -> None:
        """Build result with string value."""
        result = build_result("hello", 1)
        assert result == {"jsonrpc": "2.0", "result": "hello", "id": 1}

    def test_build_result_with_number(self) -> None:
        """Build result with number value."""
        result = build_result(42, 1)
        assert result == {"jsonrpc": "2.0", "result": 42, "id": 1}

    def test_build_result_with_dict(self) -> None:
        """Build result with dict value."""
        result = build_result({"name": "Alice", "age": 30}, 1)
        assert result == {
            "jsonrpc": "2.0",
            "result": {"name": "Alice", "age": 30},
            "id": 1,
        }

    def test_build_result_with_list(self) -> None:
        """Build result with list value."""
        result = build_result([1, 2, 3], 1)
        assert result == {"jsonrpc": "2.0", "result": [1, 2, 3], "id": 1}

    def test_build_result_with_null(self) -> None:
        """Build result with null value."""
        result = build_result(None, 1)
        assert result == {"jsonrpc": "2.0", "result": None, "id": 1}

    def test_build_result_with_boolean(self) -> None:
        """Build result with boolean value."""
        result = build_result(True, 1)
        assert result == {"jsonrpc": "2.0", "result": True, "id": 1}

    def test_build_result_with_null_id(self) -> None:
        """Build result with id: null."""
        result = build_result("ok", None)
        assert result == {"jsonrpc": "2.0", "result": "ok", "id": None}

    def test_build_result_with_string_id(self) -> None:
        """Build result with string id."""
        result = build_result("ok", "abc123")
        assert result == {"jsonrpc": "2.0", "result": "ok", "id": "abc123"}

    def test_build_result_with_nested_structures(self) -> None:
        """Build result with nested structures."""
        result = build_result(
            {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]},
            1,
        )
        assert result["result"]["users"][0]["name"] == "Alice"

    def test_build_result_with_empty_dict(self) -> None:
        """Build result with empty dict."""
        result = build_result({}, 1)
        assert result == {"jsonrpc": "2.0", "result": {}, "id": 1}

    def test_build_result_with_empty_list(self) -> None:
        """Build result with empty list."""
        result = build_result([], 1)
        assert result == {"jsonrpc": "2.0", "result": [], "id": 1}


class TestJsonRpcRequest:
    """Test JsonRpcRequest dataclass."""

    def test_json_rpc_request_is_frozen(self) -> None:
        """JsonRpcRequest is frozen (immutable)."""
        req = JsonRpcRequest(method="add", params={"a": 1}, id=1, is_notification=False)
        with pytest.raises(dataclasses.FrozenInstanceError):
            req.method = "sub"  # pyright: ignore[reportAttributeAccessIssue]

    def test_json_rpc_request_all_fields(self) -> None:
        """JsonRpcRequest with all fields set."""
        req = JsonRpcRequest(
            method="user.getById",
            params={"user_id": 42},
            id="req-123",
            is_notification=False,
        )
        assert req.method == "user.getById"
        assert req.params == {"user_id": 42}
        assert req.id == "req-123"
        assert req.is_notification is False

    def test_json_rpc_request_notification(self) -> None:
        """JsonRpcRequest for notification."""
        req = JsonRpcRequest(
            method="log", params={"msg": "hello"}, id=None, is_notification=True
        )
        assert req.method == "log"
        assert req.params == {"msg": "hello"}
        assert req.id is None
        assert req.is_notification is True

    def test_json_rpc_request_without_params(self) -> None:
        """JsonRpcRequest without params."""
        req = JsonRpcRequest(method="ping", params=None, id=1, is_notification=False)
        assert req.method == "ping"
        assert req.params is None
        assert req.id == 1
        assert req.is_notification is False

    def test_json_rpc_request_with_list_params(self) -> None:
        """JsonRpcRequest with list params."""
        req = JsonRpcRequest(method="add", params=[1, 2], id=1, is_notification=False)
        assert req.params == [1, 2]

    def test_json_rpc_request_equality(self) -> None:
        """JsonRpcRequest equality."""
        req1 = JsonRpcRequest(
            method="add", params={"a": 1}, id=1, is_notification=False
        )
        req2 = JsonRpcRequest(
            method="add", params={"a": 1}, id=1, is_notification=False
        )
        assert req1 == req2

    def test_json_rpc_request_inequality(self) -> None:
        """JsonRpcRequest inequality."""
        req1 = JsonRpcRequest(
            method="add", params={"a": 1}, id=1, is_notification=False
        )
        req2 = JsonRpcRequest(
            method="sub", params={"a": 1}, id=1, is_notification=False
        )
        assert req1 != req2
