"""Core JSON-RPC implementation.

Request handling, dispatch, and extension points (parser, builder, exception mapper).
"""

# pyright: reportPrivateUsage=false

import asyncio
import contextlib
import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from wilrise.context import RpcContext
from wilrise.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RpcError,
)
from wilrise.extensions import (
    ExceptionMapper,
    ParsedRequest,
    RequestLogger,
    RequestParser,
    ResponseBuilder,
)
from wilrise.params import (
    BaseModel,
    Param,
    ParamsValidationError,
    PydanticValidationError,
    Use,
    _effective_annotation,
    _validate_param,
    get_param_meta,
)
from wilrise.protocol import build_error, build_result, parse_single_request

logger = logging.getLogger(__name__)


class _DefaultRequestParser:
    """Default request parser: JSON-RPC 2.0 via protocol.parse_single_request."""

    def parse(
        self,
        body: dict[str, Any],
        request: Request,
    ) -> tuple[ParsedRequest | None, dict[str, Any] | None]:
        parsed, invalid_data = parse_single_request(body)
        if parsed is None:
            return None, invalid_data
        return (
            ParsedRequest(
                method=parsed.method,
                params=parsed.params,
                id=parsed.id,
                is_notification=parsed.is_notification,
            ),
            None,
        )


class _DefaultResponseBuilder:
    """Default response builder: JSON-RPC 2.0 via protocol.build_*."""

    def build_result(self, result: Any, req_id: Any) -> dict[str, Any]:
        return build_result(result, req_id)

    def build_error(
        self,
        code: int,
        message: str,
        req_id: Any,
        *,
        data: Any = None,
    ) -> dict[str, Any]:
        return build_error(code, message, req_id, data=data)


_default_request_parser = _DefaultRequestParser()
_default_response_builder = _DefaultResponseBuilder()

# RPC hook: (method_name, params, request) -> error_response dict or None
BeforeCallHook = Callable[
    [str, dict[str, Any] | list[Any] | None, Request],
    dict[str, Any] | None | Awaitable[dict[str, Any] | None],
]
# RPC hook: (method_name, result, request) -> None
AfterCallHook = Callable[
    [str, Any, Request],
    None | Awaitable[None],
]


def _method_decorator(
    methods_map: dict[str, Callable[..., Any]],
    name_or_fn: str | Callable[..., Any],
) -> Callable[..., Any] | Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a function into methods_map; supports route-style naming."""

    def register(rpc_name: str, f: Callable[..., Any]) -> Callable[..., Any]:
        f._wilrise_method = True  # type: ignore[attr-defined]
        f._wilrise_rpc_name = rpc_name  # type: ignore[attr-defined]
        methods_map[rpc_name] = f
        return f

    if callable(name_or_fn):
        return register(name_or_fn.__name__, name_or_fn)

    def _register(f: Callable[..., Any]) -> Callable[..., Any]:
        return register(name_or_fn, f)

    return _register


class Router:
    """Route group. Use @router.method, then app.include_router(router)."""

    def __init__(self) -> None:
        self._methods: dict[str, Callable[..., Any]] = {}

    def method(
        self, name_or_fn: str | Callable[..., Any]
    ) -> Callable[..., Any] | Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a function on this router; same usage as @app.method."""
        return _method_decorator(self._methods, name_or_fn)


class Wilrise:
    """JSON-RPC service. Use @app.method or include_router to register methods."""

    def __init__(
        self,
        *,
        debug: bool = False,
        max_batch_size: int = 50,
        max_request_size: int = 1024 * 1024,
        log_requests: bool = True,
        logger: logging.Logger | None = None,
        log_level: int | None = None,
    ) -> None:
        """Invariant: debug=False in production (must not leak exception text).
        max_batch_size / max_request_size enforced; size check when Content-Length set.
        """
        self._methods: dict[str, Callable[..., Any]] = {}
        self._debug = debug
        self._max_batch_size = max_batch_size
        self._max_request_size = max_request_size
        self._log_requests = log_requests
        self._logger = logger if logger is not None else logging.getLogger(__name__)
        if log_level is not None:
            self._logger.setLevel(log_level)
        self._middleware: list[tuple[type, dict[str, Any]]] = []
        self._before_call_hooks: list[BeforeCallHook] = []
        self._after_call_hooks: list[AfterCallHook] = []
        self._request_parser: RequestParser | None = None
        self._response_builder: ResponseBuilder | None = None
        self._exception_mapper: ExceptionMapper | None = None
        self._request_loggers: list[RequestLogger] = []
        self._startup: list[Callable[..., Any | Awaitable[Any]]] = []
        self._shutdown: list[Callable[..., Any | Awaitable[Any]]] = []

    def method(
        self, name_or_fn: str | Callable[..., Any]
    ) -> Callable[..., Any] | Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a function as a JSON-RPC method; supports route-style naming.

        - @app.method          → RPC method name is the function name
        - @app.method("getUser") → RPC method name is "getUser" (route style)
        """
        return _method_decorator(self._methods, name_or_fn)

    def include_router(self, router: Router, *, prefix: str = "") -> None:
        """Mount a route group on this app with an optional method name prefix."""
        for rpc_name, fn in router._methods.items():
            key = f"{prefix}{rpc_name}" if prefix else rpc_name
            if key in self._methods:
                raise ValueError(f"Duplicate method name: {key}")
            self._methods[key] = fn

    def add_middleware(self, middleware_cls: type, **kwargs: Any) -> None:
        """Add Starlette middleware. First added = outermost (executed first)."""
        self._middleware.append((middleware_cls, kwargs))

    def add_before_call_hook(self, hook: BeforeCallHook) -> None:
        """Return error dict to abort (sent as response); None to continue."""
        self._before_call_hooks.append(hook)

    def add_after_call_hook(self, hook: AfterCallHook) -> None:
        """Extension point. Run after successful method execution; return ignored."""
        self._after_call_hooks.append(hook)

    def set_request_parser(self, parser: RequestParser) -> None:
        """Custom request parser. Replaces default; return ParsedRequest."""
        self._request_parser = parser

    def set_response_builder(self, builder: ResponseBuilder) -> None:
        """Custom response builder. Replaces default; conform to §5.1."""
        self._response_builder = builder

    def set_exception_mapper(self, mapper: ExceptionMapper | None) -> None:
        """Set custom exception-to-RPC-error mapper. Pass None for default."""
        self._exception_mapper = mapper

    def add_request_logger(self, logger_fn: RequestLogger) -> None:
        """Add request completion logger. (context, duration_ms, response, error)."""
        self._request_loggers.append(logger_fn)

    def add_startup(self, fn: Callable[..., Any | Awaitable[Any]]) -> None:
        """Add a startup hook (runs once when the ASGI app starts). Sync or async."""
        self._startup.append(fn)

    def add_shutdown(self, fn: Callable[..., Any | Awaitable[Any]]) -> None:
        """Add shutdown hook (runs once when ASGI app shuts down). Sync or async."""
        self._shutdown.append(fn)

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        *,
        access_log: bool = False,
        **kwargs: Any,
    ) -> None:
        """Run the JSON-RPC app with uvicorn.

        By default access_log is False so uvicorn does not log every POST to the
        same path; use the built-in JSON-RPC style logs (log_requests=True) instead.
        Requires uvicorn to be installed.
        """
        import uvicorn

        uvicorn.run(
            self.as_asgi(),
            host=host,
            port=port,
            access_log=access_log,
            **kwargs,
        )

    async def resolve_method_params(
        self,
        method_name: str,
        params: dict[str, Any] | list[Any] | None,
        request: Request,
    ) -> list[Any]:
        """Resolve params for a registered method (for testing / advanced use).

        Returns the list of positional arguments to pass to the method.
        Raises ValueError if method_name is not registered or a required
        argument is missing. Raises ParamsValidationError on Pydantic
        validation failure.
        """
        if method_name not in self._methods:
            raise ValueError(f"Method not found: {method_name}")
        fn = self._methods[method_name]
        return await self._resolve_params(fn, params, request)

    def _get_sig(
        self, fn: Callable[..., Any]
    ) -> dict[str, tuple[int, Any, Param | None]]:
        sig = inspect.signature(fn)
        result: dict[str, tuple[int, Any, Param | None]] = {}
        for i, (name, param) in enumerate(sig.parameters.items()):
            default, param_meta = get_param_meta(param)
            # Keep non-Param defaults such as Use(get_db_session)
            if param.default is not inspect.Parameter.empty and not isinstance(
                param.default, Param
            ):
                default = param.default
            result[name] = (i, default, param_meta)
        return result

    async def _unwrap_provider_result(
        self, dep: Any, request: Request
    ) -> tuple[Any, bool]:
        """If provider returned a generator/async generator: take first yield as
        value, register gen for cleanup after RPC; return (value, True).
        Otherwise return (dep, False).
        """
        if inspect.isgenerator(dep):
            first = next(dep)
            cleanup: list[Any] | None = getattr(
                request.state, "_wilrise_gen_cleanup", None
            )
            if cleanup is None:
                cleanup = []
                request.state._wilrise_gen_cleanup = cleanup
            cleanup.append(dep)
            return (first, True)
        if inspect.isasyncgen(dep):
            first = await dep.__anext__()
            cleanup_list: list[Any] | None = getattr(
                request.state, "_wilrise_gen_cleanup", None
            )
            if cleanup_list is None:
                cleanup_list = []
                request.state._wilrise_gen_cleanup = cleanup_list
            cleanup_list.append(dep)
            return (first, True)
        return (dep, False)

    async def _close_provider_generators(self, request: Request) -> None:
        """Close all provider generators registered for this request (so their
        finally blocks run, e.g. session.close()).
        """
        cleanup: list[Any] = getattr(request.state, "_wilrise_gen_cleanup", [])
        request.state._wilrise_gen_cleanup = []
        for g in cleanup:
            try:
                if inspect.isasyncgen(g):
                    await g.aclose()
                else:
                    g.close()
            except Exception as e:
                if self._log_requests:
                    self._logger.debug(
                        "Provider generator close failed: %s",
                        e,
                        exc_info=True,
                    )

    async def _resolve_params(
        self,
        fn: Callable[..., Any],
        params: dict[str, Any] | list[Any] | None,
        request: Request,
    ) -> list[Any]:
        """Single BaseModel param with no key -> entire params as that model.
        Use providers receive Request only; results cached per request.
        """
        sig = self._get_sig(fn)
        fn_sig = inspect.signature(fn)
        param_names = list(sig.keys())
        # Normalize to dict for handling
        if isinstance(params, list):
            rpc_params = {
                param_names[i]: v for i, v in enumerate(params) if i < len(param_names)
            }
        elif isinstance(params, dict):
            rpc_params = params or {}
        else:
            rpc_params = {}

        # Single param as full params: when the param key is absent, validate
        # entire rpc_params as that BaseModel (e.g. params={"a":1,"b":2} for
        # def add(params: AddParams)); otherwise validate the value for that key.
        def _key_present(name: str, param_meta: Param | None) -> bool:
            if param_meta and param_meta.alias and param_meta.alias in rpc_params:
                return True
            return name in rpc_params

        def _get_value(name: str, param_meta: Param | None) -> Any:
            if param_meta and param_meta.alias and param_meta.alias in rpc_params:
                return rpc_params[param_meta.alias]
            return rpc_params.get(name)

        # First param is BaseModel and its key is absent: use entire rpc_params
        # for that param, then resolve the rest by key/Use/default.
        if (
            param_names
            and BaseModel is not None
            and PydanticValidationError is not None
        ):
            first_name = param_names[0]
            _, _first_default, first_meta = sig[first_name]
            first_param = fn_sig.parameters[first_name]
            first_effective = _effective_annotation(first_param.annotation)
            if (
                isinstance(first_effective, type)
                and issubclass(first_effective, BaseModel)
                and not _key_present(first_name, first_meta)
            ):
                try:
                    first_instance = first_effective.model_validate(  # type: ignore[union-attr]
                        rpc_params
                    )
                except PydanticValidationError as e:
                    raise ParamsValidationError(
                        cast(list[dict[str, Any]], e.errors())
                    ) from e
                dep_cache = getattr(request.state, "_wilrise_dep_cache", {})
                resolved = cast(
                    list[Any],
                    [first_instance] + [None] * (len(param_names) - 1),
                )
                for i in range(1, len(param_names)):
                    name = param_names[i]
                    _, default, param_meta = sig[name]
                    if _key_present(name, param_meta):
                        resolved[i] = _get_value(name, param_meta)
                    elif isinstance(default, Use):
                        key = id(default.provider)
                        if key in dep_cache:
                            resolved[i] = dep_cache[key]
                        else:
                            dep = default(request)
                            if asyncio.iscoroutine(dep):
                                dep = await dep
                            dep, is_gen = await self._unwrap_provider_result(
                                dep, request
                            )
                            if not is_gen:
                                dep_cache[key] = dep
                            resolved[i] = dep
                    elif default is not ...:
                        resolved[i] = default
                    else:
                        raise ValueError(f"Missing required argument: {name}")
                for i in range(1, len(param_names)):
                    param = fn_sig.parameters[param_names[i]]
                    resolved[i] = _validate_param(
                        param.annotation, resolved[i], param_names[i]
                    )
                return resolved

        if (
            len(param_names) == 1
            and BaseModel is not None
            and PydanticValidationError is not None
        ):
            only_name = param_names[0]
            _, default, param_meta = sig[only_name]
            only_param = fn_sig.parameters[only_name]
            effective = _effective_annotation(only_param.annotation)
            if isinstance(effective, type) and issubclass(effective, BaseModel):
                if _key_present(only_name, param_meta):
                    raw = _get_value(only_name, param_meta)
                else:
                    raw = rpc_params
                try:
                    instance = effective.model_validate(raw)  # type: ignore[union-attr]
                except PydanticValidationError as e:
                    raise ParamsValidationError(
                        cast(list[dict[str, Any]], e.errors())
                    ) from e
                return [instance]

        dep_cache: dict[int, Any] = getattr(request.state, "_wilrise_dep_cache", {})
        resolved: list[Any] = [None] * len(param_names)
        for i, name in enumerate(param_names):
            _, default, param_meta = sig[name]
            if _key_present(name, param_meta):
                resolved[i] = _get_value(name, param_meta)
            elif isinstance(default, Use):
                key = id(default.provider)
                if key in dep_cache:
                    resolved[i] = dep_cache[key]
                else:
                    dep = default(request)
                    if asyncio.iscoroutine(dep):
                        dep = await dep
                    dep, is_gen = await self._unwrap_provider_result(dep, request)
                    if not is_gen:
                        dep_cache[key] = dep
                    resolved[i] = dep
            elif default is not ...:
                resolved[i] = default
            else:
                raise ValueError(f"Missing required argument: {name}")

        # Pydantic validation per parameter
        for i, name in enumerate(param_names):
            param = fn_sig.parameters[name]
            resolved[i] = _validate_param(param.annotation, resolved[i], name)

        return resolved

    def _get_builder(self) -> ResponseBuilder:
        return self._response_builder or _default_response_builder

    def _error(
        self,
        code: int,
        message: str,
        req_id: Any,
        *,
        data: Any = None,
    ) -> dict[str, Any]:
        """Build a JSON-RPC error response. data is optional per spec §5.1."""
        return self._get_builder().build_error(code, message, req_id, data=data)

    def _invalid_request(self, req_id: Any, *, data: Any = None) -> dict[str, Any]:
        return self._error(INVALID_REQUEST, "Invalid Request", req_id, data=data)

    def _format_rpc_methods(self, methods: list[str]) -> str:
        """Format RPC method list for log: single 'method' or 'batch(n) [a, b, c]'."""
        if not methods:
            return "?"
        if len(methods) == 1:
            return methods[0]
        return f"batch({len(methods)}) [{', '.join(methods)}]"

    async def _log_request_complete(
        self,
        context: RpcContext,
        start_time: float,
        response: Response,
        error: BaseException | None = None,
    ) -> None:
        duration_ms = (time.perf_counter() - start_time) * 1000
        if self._log_requests:
            methods: list[str] = getattr(context.request.state, "_rpc_methods", [])
            method_str = self._format_rpc_methods(methods)
            self._logger.info(
                "JSON-RPC %s → %s in %.2fms",
                method_str,
                response.status_code,
                duration_ms,
                extra={
                    "request_id": context.http_request_id,
                    "rpc_methods": methods,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
        for logger_fn in self._request_loggers:
            out = logger_fn(context, duration_ms, response, error)
            if asyncio.iscoroutine(out):
                await out

    async def _process_single(
        self, body: dict[str, Any], request: Request
    ) -> dict[str, Any] | None:
        """Process one Request object.

        Returns response dict or None for notification.
        """
        parser = self._request_parser or _default_request_parser
        parsed, invalid_data = parser.parse(body, request)
        if parsed is None:
            await self._close_provider_generators(request)
            return self._invalid_request(body.get("id"), data=invalid_data)

        method_name = parsed.method
        params = parsed.params
        req_id = parsed.id
        is_notification = parsed.is_notification

        rpc_methods = getattr(request.state, "_rpc_methods", None)
        if rpc_methods is not None:
            rpc_methods.append(method_name)

        context = RpcContext(
            method=method_name,
            request_id=req_id,
            http_request_id=request.headers.get("X-Request-ID", "unknown"),
            is_notification=is_notification,
            request=request,
        )
        request.state.rpc_context = context

        if method_name not in self._methods:
            await self._close_provider_generators(request)
            if is_notification:
                return None
            return self._error(
                METHOD_NOT_FOUND,
                f"Method not found: {method_name}",
                req_id,
                data={"method": method_name},
            )

        for hook in self._before_call_hooks:
            out = hook(method_name, params, request)
            if asyncio.iscoroutine(out):
                out = await out
            if out is not None:
                await self._close_provider_generators(request)
                if is_notification:
                    return None
                return cast("dict[str, Any]", out)

        fn = self._methods[method_name]
        try:
            args = await self._resolve_params(fn, params, request)
        except ParamsValidationError as e:
            await self._close_provider_generators(request)
            if is_notification:
                return None
            return self._error(
                INVALID_PARAMS,
                "Invalid params",
                req_id,
                data={"validation_errors": e.errors},
            )
        except ValueError as e:
            # Unify -32602 data: same shape as Pydantic errors for client handling
            msg = str(e)
            validation_errors: list[dict[str, Any]] = [
                {"loc": [], "msg": msg, "type": "value_error"}
            ]
            if "Missing required argument:" in msg:
                arg_name = msg.replace("Missing required argument:", "").strip()
                validation_errors = [{"loc": [arg_name], "msg": msg, "type": "missing"}]
            await self._close_provider_generators(request)
            if is_notification:
                return None
            return self._error(
                INVALID_PARAMS,
                "Invalid params",
                req_id,
                data={"validation_errors": validation_errors},
            )
        except RpcError as e:
            await self._close_provider_generators(request)
            if is_notification:
                return None
            return self._error(e.code, e.message, req_id, data=e.data)
        except Exception as e:
            await self._close_provider_generators(request)
            if self._exception_mapper:
                mapped = self._exception_mapper.map_exception(e, context)
                if mapped is not None:
                    code, msg, data = mapped
                    if is_notification:
                        return None
                    return self._get_builder().build_error(code, msg, req_id, data=data)
            if self._log_requests:
                self._logger.error(
                    "RPC param resolution failed",
                    extra={
                        "method": method_name,
                        "request_id": req_id,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                    exc_info=True,
                )
            _err_msg = str(e) if self._debug else "Internal error"
            _err_data: dict[str, Any] | None = (
                {"type": type(e).__name__} if self._debug else None
            )
            if _err_data is not None and BaseModel is None:
                _err_data["hint"] = "Install wilrise[pydantic] for parameter validation"
            if _err_data is None:
                _err_data = {"request_id": context.http_request_id}
            if is_notification:
                return None
            return self._error(INTERNAL_ERROR, _err_msg, req_id, data=_err_data)
        try:
            result = fn(*args)
            if asyncio.iscoroutine(result):
                result = await result
        except RpcError as e:
            await self._close_provider_generators(request)
            if is_notification:
                return None
            return self._error(e.code, e.message, req_id, data=e.data)
        except Exception as e:
            await self._close_provider_generators(request)
            if self._exception_mapper:
                mapped = self._exception_mapper.map_exception(e, context)
                if mapped is not None:
                    code, msg, data = mapped
                    if is_notification:
                        return None
                    return self._get_builder().build_error(code, msg, req_id, data=data)
            if self._log_requests:
                self._logger.error(
                    "RPC method execution failed",
                    extra={
                        "method": method_name,
                        "request_id": req_id,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                    exc_info=True,
                )
            _err_msg = str(e) if self._debug else "Internal error"
            _err_data = {"type": type(e).__name__} if self._debug else None
            if _err_data is not None and BaseModel is None:
                _err_data["hint"] = "Install wilrise[pydantic] for parameter validation"
            if _err_data is None:
                _err_data = {"request_id": context.http_request_id}
            if is_notification:
                return None
            return self._error(INTERNAL_ERROR, _err_msg, req_id, data=_err_data)

        if is_notification:
            await self._close_provider_generators(request)
            return None
        # Ensure result is JSON-serializable; return -32603 on failure
        try:
            json.dumps(result)
        except (TypeError, ValueError) as e:
            if self._log_requests:
                self._logger.error(
                    "RPC result not JSON-serializable",
                    extra={
                        "method": method_name,
                        "request_id": req_id,
                        "error_message": str(e),
                    },
                )
            ser_msg = str(e) if self._debug else "Result is not JSON-serializable"
            ser_data: dict[str, Any] | None = (
                {"type": type(e).__name__} if self._debug else None
            )
            if ser_data is None:
                ser_data = {"request_id": context.http_request_id}
            await self._close_provider_generators(request)
            return self._error(INTERNAL_ERROR, ser_msg, req_id, data=ser_data)
        for hook in self._after_call_hooks:
            out = hook(method_name, result, request)
            if asyncio.iscoroutine(out):
                await out
        await self._close_provider_generators(request)
        return self._get_builder().build_result(result, req_id)

    def _schedule_background_tasks(self, request: Request) -> None:
        """Schedule request.state.background_tasks (fire-and-forget after response)."""
        tasks = getattr(request.state, "background_tasks", None)
        if not tasks:
            return
        for t in tasks:
            c = t() if callable(t) else t
            if asyncio.iscoroutine(c):
                asyncio.create_task(c)

    async def _handle_request(self, request: Request) -> Response:
        """Single HTTP entry: POST only; batch/single dispatch, then _process_single."""
        request.state._wilrise_dep_cache = {}
        request.state._wilrise_gen_cleanup = []
        request.state.background_tasks = []
        # RPC method names for this HTTP request (for logging)
        request.state._rpc_methods = []
        http_request_id = request.headers.get("X-Request-ID", "unknown")
        start_time = time.perf_counter()
        top_context = RpcContext(
            method="",
            request_id=None,
            http_request_id=http_request_id,
            is_notification=False,
            request=request,
        )

        if request.method != "POST":
            r = JSONResponse(
                self._invalid_request(None),
                status_code=405,
            )
            await self._log_request_complete(top_context, start_time, r)
            self._schedule_background_tasks(request)
            return r

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                cl = int(content_length)
            except ValueError:
                cl = -1
            if cl > self._max_request_size:
                if self._log_requests:
                    self._logger.warning(
                        "Request body too large",
                        extra={
                            "request_id": http_request_id,
                            "content_length": cl,
                            "max_request_size": self._max_request_size,
                        },
                    )
                r = JSONResponse(
                    self._error(INVALID_REQUEST, "Request body too large", None),
                    status_code=413,
                )
                await self._log_request_complete(top_context, start_time, r)
                self._schedule_background_tasks(request)
                return r

        try:
            body = await request.json()
        except Exception:
            r = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": PARSE_ERROR, "message": "Parse error"},
                    "id": None,
                },
                status_code=400,
            )
            await self._log_request_complete(top_context, start_time, r)
            self._schedule_background_tasks(request)
            return r

        if isinstance(body, list):
            batch: list[dict[str, Any]] = cast(list[dict[str, Any]], body)
            if len(batch) > self._max_batch_size:
                if self._log_requests:
                    self._logger.warning(
                        "Batch size exceeded",
                        extra={
                            "request_id": http_request_id,
                            "batch_size": len(batch),
                            "max_batch_size": self._max_batch_size,
                        },
                    )
                r = JSONResponse(
                    self._invalid_request(
                        None,
                        data={
                            "reason": "batch_size_exceeded",
                            "batch_size": len(batch),
                            "max_batch_size": self._max_batch_size,
                        },
                    ),
                    status_code=400,
                )
                await self._log_request_complete(top_context, start_time, r)
                self._schedule_background_tasks(request)
                return r
            if len(batch) == 0:
                r = JSONResponse(
                    self._invalid_request(None),
                    status_code=400,
                )
                await self._log_request_complete(top_context, start_time, r)
                self._schedule_background_tasks(request)
                return r
            responses: list[dict[str, Any]] = []
            for item in batch:
                if not isinstance(item, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
                    responses.append(self._invalid_request(None))
                else:
                    resp = await self._process_single(item, request)
                    if resp is not None:
                        responses.append(resp)
            if len(responses) == 0:
                r = Response(status_code=204)
            else:
                r = JSONResponse(responses, status_code=200)
            await self._log_request_complete(top_context, start_time, r)
            self._schedule_background_tasks(request)
            return r

        if isinstance(body, dict):
            single_body = cast(dict[str, Any], body)
            resp = await self._process_single(single_body, request)
            if resp is None:
                r = Response(status_code=204)
            else:
                r = JSONResponse(resp, status_code=200)
            await self._log_request_complete(top_context, start_time, r)
            self._schedule_background_tasks(request)
            return r

        r = JSONResponse(
            self._invalid_request(None),
            status_code=400,
        )
        await self._log_request_complete(top_context, start_time, r)
        self._schedule_background_tasks(request)
        return r

    def as_asgi(self, path: str = "/") -> Starlette:
        """Return a Starlette ASGI application with JSON-RPC at the given path.

        If add_startup/add_shutdown were used, their hooks run when the app
        starts and shuts down (same semantics as Starlette lifespan).
        """

        async def jsonrpc_endpoint(request: Request) -> Response:
            return await self._handle_request(request)

        route = Route(path, endpoint=jsonrpc_endpoint, methods=["POST"])
        middleware_list = [
            Middleware(cls, **kwargs) for cls, kwargs in self._middleware
        ]
        lifespan = None
        if self._startup or self._shutdown:

            @contextlib.asynccontextmanager
            async def _lifespan(app: Any):
                for fn in self._startup:
                    out = fn()
                    if asyncio.iscoroutine(out):
                        await out
                try:
                    yield
                finally:
                    for fn in reversed(self._shutdown):
                        out = fn()
                        if asyncio.iscoroutine(out):
                            await out

            lifespan = _lifespan
        return Starlette(
            routes=[route],
            middleware=middleware_list,
            lifespan=lifespan,
        )

    def mount(self, app: Starlette, path: str = "/") -> None:
        """Mount the JSON-RPC endpoint on an existing Starlette application.

        Adds a POST route at the given path. Does not add any middleware
        configured on this Wilrise instance; add middleware to the target
        app instead.
        """

        async def jsonrpc_endpoint(request: Request) -> Response:
            return await self._handle_request(request)

        app.routes.append(Route(path, endpoint=jsonrpc_endpoint, methods=["POST"]))
